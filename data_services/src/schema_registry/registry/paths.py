def table_prefix(department_id: str, dataset_slug: str, table_slug: str) -> str:
    """The one place the storage layout is defined. Every path below is
    built from this -- changing the folder structure for every department/
    dataset/table this project will ever handle means changing this
    function, not hunting down f-strings scattered across pipeline.py,
    lookups.py, and openmetadata/publish.py."""

    return f"department/{department_id}/{dataset_slug}/{table_slug}"


def raw_schema_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/schemas/{timestamp}.csv"


def raw_source_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str, ext: str) -> str:
    """The department's submission exactly as it arrived, kept next to the
    parser's own raw output: raw/schemas/ is derived data, so a parser bug
    there would otherwise destroy the only evidence of what was submitted."""

    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/source/{timestamp}{ext}"


def raw_source_hash_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    """SHA-256 sidecar for the stored submission -- lets anyone verify the
    stored copy still matches what the department sent."""

    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/source/{timestamp}.sha256"


def diff_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    """Per-run change diff (added/removed/changed columns) so a run's effect
    is reviewable without diffing two snapshot CSVs by hand."""

    return f"{table_prefix(department_id, dataset_slug, table_slug)}/diffs/{timestamp}.csv"


def curated_schema_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/curated/schemas/{timestamp}.csv"


def curated_schemas_prefix(department_id: str, dataset_slug: str, table_slug: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/curated/schemas/"


def pipeline_lock_path(department_id: str, dataset_slug: str, table_slug: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/pipeline"


def raw_source_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str, filename: str) -> str:
    """The original submission a run parsed, kept byte for byte next to the
    raw schema it produced (same timestamp)."""

    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/source/{timestamp}__{filename}"


def dataset_source_path(department_id: str, dataset_slug: str, timestamp: str, filename: str) -> str:
    """An original submission covering several tables of one dataset (e.g.
    a multi-table Field Dictionary), kept once at dataset level."""

    return f"department/{department_id}/{dataset_slug}/_source/{timestamp}__{filename}"


def raw_source_prefix(department_id: str, dataset_slug: str, table_slug: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/source/"


def dataset_source_prefix(department_id: str, dataset_slug: str) -> str:
    return f"department/{department_id}/{dataset_slug}/_source/"
