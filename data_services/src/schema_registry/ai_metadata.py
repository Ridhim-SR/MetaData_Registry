"""Draft column descriptions and tags with Claude, for a person to review.

    python3 -m src.schema_registry.ai_metadata samples/pwd_vishwakarma_full_raw_columns.txt

- Writes  <raw file>_metadata.csv  next to the raw file: name, business_description, tag.
  Review it, then load it with:  add <raw file> ... --metadata <that csv>
- Prints a suggested dataset description and classification. Nothing is
  written for them: copy them into catalog.yaml yourself once the dataset is there.

Only field names and types are sent to Claude, never records. It is a manual
step run ahead of `add`; the pipeline itself never calls it.
Needs ANTHROPIC_API_KEY in .env.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.schema_registry.add import guess_format
from src.schema_registry.pipeline import parse_source
from src.utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-5-5"
DEFAULT_DEFINITIONS = Path(__file__).resolve().parents[2] / "samples" / "cat_definitions.txt"
KNOWN_TAGS = ("Financial", "Firm/Contractor-Identifier", "Geospatial", "Status/Workflow", "Date/Timestamp")


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
- "dataset": {{"description": <one or two sentences on what the table holds>, {category}, "reason": <one line>}}
Return only the JSON.

Fields:
{fields}"""


def draft(columns: list[dict], definitions: str | None) -> dict:
    import anthropic  # not needed by the rest of the pipeline

    reply = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
        model=MODEL, max_tokens=16000, messages=[{"role": "user", "content": _prompt(columns, definitions)}]
    )
    text = reply.content[0].text
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def write_csv(path: Path, columns: list[dict], drafted: list[dict]) -> int:
    """One row per raw field, in the raw file's order; a field Claude skipped is left blank."""

    by_name = {d.get("name"): d for d in drafted}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "business_description", "tag"])
        for c in columns:
            d = by_name.get(c["name"], {})
            writer.writerow([c["name"], d.get("business_description", ""), d.get("tag", "")])
    return sum(1 for c in columns if c["name"] not in by_name)


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
    definitions = definitions_file.read_text() if definitions_file.is_file() else None

    logger.info(f"Asking {MODEL} about {len(columns)} field(s) (names and types only)...")
    result = draft(columns, definitions)

    out = raw.with_name(f"{raw.stem}_metadata.csv")
    missing = write_csv(out, columns, result.get("columns", []))
    print(f"\nColumn descriptions and tags -> {out}  ({len(columns) - missing} of {len(columns)} drafted)")
    print("Review it, then:  add <raw file> ... --metadata", out)

    ds = result.get("dataset", {})
    print("\nDataset (enter these in catalog.yaml yourself):")
    print(f"  description: {ds.get('description', '')}")
    print(f"  category:    {ds.get('category') or '(none -- no definitions file found)'}")
    print(f"  why:         {ds.get('reason', '')}")
    return 0


if __name__ == "__main__":
    from src.utils.cli import run_cli

    sys.exit(run_cli("ai_metadata", _main, sys.argv[1:]))
