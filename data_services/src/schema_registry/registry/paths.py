def table_prefix(department_id: str, dataset_slug: str, table_slug: str) -> str:
    """The one place the storage layout is defined. Every path below is
    built from this -- changing the folder structure for every department/
    dataset/table this project will ever handle means changing this
    function, not hunting down f-strings scattered across pipeline.py,
    lookups.py, and openmetadata/publish.py."""

    return f"department/{department_id}/{dataset_slug}/{table_slug}"


def raw_schema_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/raw/schemas/{timestamp}.csv"


def curated_schema_path(department_id: str, dataset_slug: str, table_slug: str, timestamp: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/curated/schemas/{timestamp}.csv"


def curated_schemas_prefix(department_id: str, dataset_slug: str, table_slug: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/curated/schemas/"


def pipeline_lock_path(department_id: str, dataset_slug: str, table_slug: str) -> str:
    return f"{table_prefix(department_id, dataset_slug, table_slug)}/pipeline"
