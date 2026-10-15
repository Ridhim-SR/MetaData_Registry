"""Draft column descriptions and tags with Claude, for a person to review.

    python3 -m src.schema_registry.ai_metadata samples/pwd_vishwakarma_full_raw_columns.txt

- Writes  <raw file>_metadata.csv  next to the raw file: name, business_description, tag.
  Review it, then load it with:  add <raw file> ... --metadata <that csv>
- Prints a suggested dataset description and classification. Nothing is
  written for them: copy them into catalog.yaml yourself once the dataset is there.
- Identifier and sensitive-attribute tags (PII / Sensitive) are applied by rules from the
  MeitY Model Data Sharing Framework (s5.1), not left to the model. Any PII column forces
  the table to CAT-3 at minimum. A dataset's category is the HIGHEST across its tables,
  so take the maximum yourself when you enter it in catalog.yaml.

Only field names and types are sent to Claude, never records. It is a manual
step run ahead of `add`; the pipeline itself never calls it.
Needs ANTHROPIC_API_KEY in .env.
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.schema_registry.add import guess_format
from src.schema_registry.pipeline import parse_source
from src.utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-5-5"
DEFAULT_DEFINITIONS = Path(__file__).resolve().parents[2] / "samples" / "cat_definitions.txt"
KNOWN_TAGS = (
    "PII", "Sensitive", "Financial", "Firm/Contractor-Identifier",
    "Geospatial", "Status/Workflow", "Date/Timestamp",
)
CATEGORY_ORDER = ["CAT-1", "CAT-2", "CAT-3", "CAT-4"]

# Framework s5.1 direct identifiers and quasi-identifiers -> PII.
# `ration` is anchored ((^|_)ration): as a bare alternative it matched the
# "ration" inside "regiSTRATION", so registration_id and
# vendor_registration_id were being tagged PII for a substring reason rather
# than because they identify anyone. Anchored, it still catches ration_card
# / rashan_card (and only those), and registration_no stays covered by its
# own alternative. `mobile_verified` is deliberately not excluded here --
# NOT_PII below handles it, because "mobile" is a match anywhere.
DIRECT_ID = re.compile(
    r"(^name$|farmer_name|father_name|vendor_name|hindi_(name|father_name|address)|"
    r"mobile|email|aadh?a{1,2}r|adhar|pan_?(no|number)|passport|voter|licen[cs]e|"
    r"account_no|account_number|registration_no|rashan|(^|_)ration|"
    r"(^|_)address$|date_of_birth|(^|_)dob$|^image$|photo)",
    re.I,
)
NOT_PII = re.compile(r"mobile_verified", re.I)  # a status flag, not the number itself
# Framework s5.1 sensitive attributes -> Sensitive
SENSITIVE = re.compile(r"(caste|religion|disab|health|criminal|migrat)", re.I)


def _prompt(columns: list[dict], definitions: str | None) -> str:
    fields = "\n".join(f"- {c['name']} ({c['data_type']})" for c in columns)
    category = (
        f'"category": the one dataset classification that fits, chosen only from these definitions:\n{definitions}'
        if definitions else '"category": "" (no definitions were given)'
    )
    return f"""You are documenting a government department's database table for a data catalogue.
From the field names and types only, return JSON with:
- "columns": a list with one object per field: {{"name": <exactly as given>, "business_description": <one plain sentence>, "tag": <short label or "">}}.
  Prefer these tags when they fit: {", ".join(KNOWN_TAGS)}. Leave tag "" if none fits. If a name is unclear, say so in the description rather than guessing.
  Use PII only for a direct identifier of a person or an account: their name (farmer_name, father_name,
  vendor_name and the hindi_* forms), Aadhaar, PAN, passport, voter ID, driving licence, mobile number,
  email, residential address, date of birth, photograph, bank account number, ration card number, or a
  registration number. registration_id / vendor_registration_id are internal keys, not identifiers, and
  a verification flag such as mobile_verified is not the number it refers to -- neither is PII.
  Use Sensitive for caste, religion, health, disability, criminal record or migration status.
  PII and Sensitive are re-applied from the MDSF s5.1 rules after you answer, so a tag that disagrees
  with them is discarded; a tag the rules do not cover is kept as you wrote it.
- "dataset": {{"description": <one or two sentences on what the table holds>, {category}, "reason": <one line>}}
Return only the JSON.

Fields:
{fields}"""


def draft(columns: list[dict], definitions: str | None) -> dict:
    import anthropic  # not needed by the rest of the pipeline

    reply = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
        model=MODEL, max_tokens=16000, messages=[{"role": "user", "content": _prompt(columns, definitions)}]
    )
    if reply.stop_reason == "max_tokens":
        raise RuntimeError("Response was cut off; split the table into smaller files or raise max_tokens")
    text = reply.content[0].text
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def apply_rules(columns: list[dict], drafted: list[dict]) -> tuple[list[dict], list[str]]:
    """Rule-based PII / Sensitive tags override the model. PII wins over Financial.

    Also adds an entry for any field the model skipped, so the rules still cover it.
    Returns (drafted, names whose tag the rules changed) so the changes can be reviewed.
    """

    by_name = {d.get("name"): d for d in drafted}
    changed: list[str] = []
    for c in columns:
        d = by_name.setdefault(c["name"], {"name": c["name"], "business_description": "", "tag": ""})
        name = c["name"]
        if DIRECT_ID.search(name) and not NOT_PII.search(name):
            new = "PII"
        elif SENSITIVE.search(name):
            new = "Sensitive"
        else:
            continue
        if d.get("tag") != new:
            changed.append(f"{name}: '{d.get('tag', '')}' -> {new}")
            d["tag"] = new
    return list(by_name.values()), changed


def category_floor(drafted: list[dict], model_category: str | None) -> str:
    """Never accept a category lower than the data allows: any PII or Sensitive column means CAT-3."""

    floor = "CAT-3" if any(d.get("tag") in ("PII", "Sensitive") for d in drafted) else "CAT-1"
    if model_category not in CATEGORY_ORDER:
        return floor
    return max(model_category, floor, key=CATEGORY_ORDER.index)


def write_csv(path: Path, columns: list[dict], drafted: list[dict]) -> int:
    """One row per raw field, in the raw file's order; a field Claude skipped is left blank."""

    by_name = {d.get("name"): d for d in drafted}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "business_description", "tag"])
        for c in columns:
            d = by_name.get(c["name"], {})
            writer.writerow([c["name"], d.get("business_description", ""), d.get("tag", "")])
    return sum(1 for c in columns if not by_name.get(c["name"], {}).get("business_description"))


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m src.schema_registry.ai_metadata", description=__doc__.split("\n\n")[0])
    parser.add_argument("raw_file")
    parser.add_argument("--cat-definitions", default=str(DEFAULT_DEFINITIONS),
                        help="text file describing CAT-1 to CAT-4 (default: samples/cat_definitions.txt)")
    args = parser.parse_args(argv)

    load_dotenv()
    raw = Path(args.raw_file)
    if not raw.is_file():
        raise FileNotFoundError(f"No such file: {raw} -- check the path")
    columns = parse_source("", raw.stem, guess_format(raw.name), raw.read_text(encoding="utf-8-sig"))
    definitions_file = Path(args.cat_definitions)
    definitions = definitions_file.read_text(encoding="utf-8") if definitions_file.is_file() else None

    logger.info(f"Asking {MODEL} about {len(columns)} field(s) (names and types only)...")
    result = draft(columns, definitions)

    drafted, changed = apply_rules(columns, result.get("columns", []))
    out = raw.with_name(f"{raw.stem}_metadata.csv")
    undescribed = write_csv(out, columns, drafted)
    print(f"\nColumn descriptions and tags -> {out}  ({len(columns) - undescribed} of {len(columns)} described)")
    print("Review it, then:  add <raw file> ... --metadata", out)
    if changed:
        print(f"\nTags set or changed by the framework rules ({len(changed)}), please review:")
        for line in changed:
            print(f"  {line}")

    ds = result.get("dataset", {})
    category = category_floor(drafted, ds.get("category"))
    print("\nDataset (enter these in catalog.yaml yourself):")
    print(f"  description: {ds.get('description', '')}")
    print(f"  category:    {category}  (model said: {ds.get('category') or 'none'})")
    print(f"  why:         {ds.get('reason', '')}")
    print("  note:        a dataset's category is the highest across all its tables")
    return 0


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("ai_metadata", _main, sys.argv[1:]))
