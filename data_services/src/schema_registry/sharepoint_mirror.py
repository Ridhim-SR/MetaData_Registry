"""Copy the curated schema output (and each dataset's details) to SharePoint.

Wasabi remains the system of record. This module is the small, optional
read-only mirror non-technical users get:

    department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<ts>.csv
    department/<department_id>/<dataset_slug>/dataset_details.txt

Raw submissions, parser output, diffs and the registry lookups are
deliberately not mirrored -- only the files a reviewer needs.

The mirror is switched off unless SharePoint settings are set (see
src/storage/sharepoint.py). Failures are logged and swallowed on the ingest
path: the Wasabi write already succeeded and must not be reported as failed
because SharePoint was unreachable.

Publish or refresh the read-only SharePoint view with:
    python3 -m src.schema_registry.sharepoint_mirror
"""

import argparse
import os

from src.schema_registry.catalog import DepartmentEntry, DatasetEntry, load_catalog
from src.schema_registry.registry import lookups, paths
from src.storage.base import ObjectStorage
from src.storage.sharepoint import SharePointMirror, mirror_from_env
from src.utils.config import MAIN_BRANCH, _current_branch
from src.utils.logger import get_logger

logger = get_logger(__name__)

# datasets.csv field -> label in dataset_details.txt, in reading order.
DETAIL_FIELDS = (
    ("category", "Category"),
    ("dataset_type", "Dataset Type"),
    ("schema_source", "Schema Source"),
    ("owner", "Owner"),
    ("steward", "Steward"),
    ("frequency", "Frequency"),
    ("timeline", "Timeline"),
    ("api_available", "API Available"),
    ("dataset_description", "Description"),
)


def _require_main_branch() -> None:
    branch = _current_branch()
    if branch != MAIN_BRANCH:
        where = f"'{branch}'" if branch else "an unknown branch"
        raise PermissionError(
            f"SharePoint mirroring is allowed only on the '{MAIN_BRANCH}' branch; "
            f"currently on {where}. Merge the reviewed changes and check out "
            f"'{MAIN_BRANCH}' before running the mirror."
        )


def dataset_details_text(department_id: str, department_name: str, dataset_name: str,
                         fields: dict) -> str:
    """A deterministic plain-text summary."""

    dataset_id = f"{department_id}.{lookups.slugify(dataset_name)}"
    lines = [
        "Dataset Details",
        "===============",
        "",
        f"Department:    {department_name or department_id}",
        f"Department ID: {department_id}",
        f"Dataset:       {dataset_name}",
        f"Dataset ID:    {dataset_id}",
        "",
    ]
    for key, label in DETAIL_FIELDS:
        value = (fields.get(key) or "").strip()
        if key == "dataset_description":
            lines.append(f"{label}:")
            lines.extend(f"  {line}" for line in (value.splitlines() or [""]))
        else:
            lines.append(f"{label}: {value}".rstrip())
    return "\n".join(lines).rstrip() + "\n"


def mirror_curated_snapshot(mirror: SharePointMirror, storage: ObjectStorage,
                            department_id: str, dataset_slug: str, table_slug: str,
                            timestamp: str) -> str | None:
    """Upload one curated snapshot, read from storage so SharePoint receives
    are exactly the bytes in Wasabi."""

    key = paths.curated_schema_path(department_id, dataset_slug, table_slug, timestamp)
    data = storage.read_bytes(key)
    return mirror.upload_bytes(key, data, mimetype="text/csv", compare_latest=True)


def mirror_latest_curated(mirror: SharePointMirror, storage: ObjectStorage,
                          department_id: str, dataset_slug: str, table_slug: str) -> str | None:
    """Upload a table's newest curated snapshot (used by the backfill)."""

    try:
        key = lookups.latest_curated_snapshot_path(storage, department_id, dataset_slug, table_slug)
    except FileNotFoundError:
        logger.warning(
            f"SharePoint: no curated snapshot for {department_id}.{dataset_slug}.{table_slug} -- skipped"
        )
        return None
    return mirror.upload_bytes(key, storage.read_bytes(key), mimetype="text/csv", compare_latest=True)


def mirror_dataset_details(mirror: SharePointMirror, department_id: str, department_name: str,
                           dataset_name: str, fields: dict) -> str | None:
    dataset_slug = lookups.slugify(dataset_name)
    key = paths.dataset_details_path(department_id, dataset_slug)
    text = dataset_details_text(department_id, department_name, dataset_name, fields)
    return mirror.upload_text(key, text, mimetype="text/plain", skip_if_unchanged=True)


def mirror_after_run(storage: ObjectStorage, department_id: str, department_name: str,
                     dataset_name: str, dataset_slug: str, table_slug: str,
                     timestamp: str) -> None:
    """Best-effort mirror of what one pipeline run just wrote.

    Called after the curated snapshot and dataset registry row exist in
    storage. Any failure (unconfigured SharePoint, network, permissions) is
    logged and ignored so an ingest is never failed by its optional mirror."""

    try:
        mirror = mirror_from_env()
    except Exception as exc:  # noqa: BLE001 -- config error still must not fail ingest
        logger.error(f"SharePoint mirror skipped: {exc}")
        return
    if mirror is None:
        return

    try:
        mirror_curated_snapshot(
            mirror, storage, department_id, dataset_slug, table_slug, timestamp
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"SharePoint: could not mirror curated snapshot for "
            f"{department_id}.{dataset_slug}.{table_slug}: {exc}"
        )

    try:
        fields = lookups.get_dataset(storage, f"{department_id}.{dataset_slug}") or {}
        mirror_dataset_details(
            mirror, department_id, department_name, dataset_name, fields
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"SharePoint: could not mirror dataset details for "
            f"{department_id}.{dataset_slug}: {exc}"
        )


def mirror_dataset_from_catalog(storage: ObjectStorage, department: DepartmentEntry,
                                dataset: DatasetEntry) -> None:
    """Mirror a dataset's details exactly as catalog.yaml describes it.

    sync calls this after set_dataset_fields(), so fields that only exist in
    the catalog (dataset_type, schema_source) are reflected even though a
    pipeline run never received them. Best effort, like mirror_after_run()."""

    try:
        mirror = mirror_from_env()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"SharePoint mirror skipped: {exc}")
        return
    if mirror is None:
        return
    try:
        mirror_dataset_details(
            mirror, department.id, department.name, dataset.name, dataset.fields
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"SharePoint: could not mirror dataset details for "
            f"{department.id}.{lookups.slugify(dataset.name)}: {exc}"
        )


def _table_slugs(storage: ObjectStorage, dataset_id: str, dataset: DatasetEntry) -> list[str]:
    """Every table of a dataset: catalog tables plus whatever a Field
    Dictionary registered in the lookups (those aren't listed in catalog)."""

    slugs = {lookups.slugify(table.name) for table in dataset.tables}
    if storage.exists(lookups.TABLES_PATH):
        slugs.update(
            row["table_id"].rsplit(".", 1)[-1]
            for row in storage.read_csv(lookups.TABLES_PATH)
            if row.get("dataset_id") == dataset_id and not row.get("deleted")
        )
    return sorted(slugs)


def mirror_all(storage: ObjectStorage, departments: list[DepartmentEntry],
               mirror: SharePointMirror | None = None) -> list[str]:
    """Backfill SharePoint from what is already in storage. Returns what it did."""

    _require_main_branch()
    mirror = mirror or mirror_from_env()
    if mirror is None:
        raise ValueError(
            "SharePoint mirroring is not configured -- set SHAREPOINT_* "
            "settings (see .env.example)"
        )

    done: list[str] = []
    for department in departments:
        for dataset in department.datasets:
            dataset_slug = lookups.slugify(dataset.name)
            dataset_id = f"{department.id}.{dataset_slug}"
            mirror_dataset_details(
                mirror, department.id, department.name, dataset.name, dataset.fields
            )
            done.append(paths.dataset_details_path(department.id, dataset_slug))
            for table_slug in _table_slugs(storage, dataset_id, dataset):
                if mirror_latest_curated(
                    mirror, storage, department.id, dataset_slug, table_slug
                ):
                    done.append(
                        lookups.latest_curated_snapshot_path(
                            storage, department.id, dataset_slug, table_slug
                        )
                    )
    return done


def _main(argv: list[str]) -> int:
    from src.storage import storage_from_env
    from src.utils.config import load_env

    parser = argparse.ArgumentParser(
        prog="python3 -m src.schema_registry.sharepoint_mirror",
        description="Copy curated schema snapshots and dataset details to SharePoint",
    )
    parser.add_argument("--catalog", default=os.path.join(os.path.dirname(__file__), "..", "..", "catalog.yaml"))
    parser.add_argument("--department", help="only this department (e.g. pwd)")
    parser.add_argument("--dry-run", action="store_true", help="show what would be uploaded")
    args = parser.parse_args(argv)

    load_env()
    _require_main_branch()
    storage = storage_from_env()
    departments = load_catalog(args.catalog)
    if args.department:
        departments = [d for d in departments if d.id == args.department]
        if not departments:
            parser.error(f"Department '{args.department}' isn't in catalog.yaml")

    if args.dry_run:
        print("Would mirror these paths under SHAREPOINT_FOLDER_PATH:")
        for department in departments:
            for dataset in department.datasets:
                dataset_id = f"{department.id}.{lookups.slugify(dataset.name)}"
                print(f"  {paths.dataset_details_path(department.id, lookups.slugify(dataset.name))}")
                for table_slug in _table_slugs(storage, dataset_id, dataset):
                    print(f"  department/{department.id}/{lookups.slugify(dataset.name)}/"
                          f"{table_slug}/curated/schemas/<latest>.csv")
        return 0

    done = mirror_all(storage, departments)
    print(f"Mirrored {len(done)} file(s) to SharePoint:")
    for path in done:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    import sys

    from src.utils.cli import run_cli

    sys.exit(run_cli("sharepoint_mirror", _main, sys.argv[1:]))
