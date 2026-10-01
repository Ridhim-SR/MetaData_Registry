from src.schema_registry.registry import paths


def test_table_prefix_shape():
    assert paths.table_prefix("pwd", "vishwakarma", "t1") == "department/pwd/vishwakarma/t1"


def test_raw_schema_path():
    assert (
        paths.raw_schema_path("pwd", "vishwakarma", "t1", "20260101T000000Z")
        == "department/pwd/vishwakarma/t1/raw/schemas/20260101T000000Z.csv"
    )


def test_curated_schema_path():
    assert (
        paths.curated_schema_path("pwd", "vishwakarma", "t1", "20260101T000000Z")
        == "department/pwd/vishwakarma/t1/curated/schemas/20260101T000000Z.csv"
    )


def test_curated_schemas_prefix_ends_with_slash():
    prefix = paths.curated_schemas_prefix("pwd", "vishwakarma", "t1")
    assert prefix == "department/pwd/vishwakarma/t1/curated/schemas/"


def test_pipeline_lock_path():
    assert paths.pipeline_lock_path("pwd", "vishwakarma", "t1") == "department/pwd/vishwakarma/t1/pipeline"


def test_different_tables_never_collide():
    a = paths.table_prefix("pwd", "vishwakarma", "t1")
    b = paths.table_prefix("pwd", "vishwakarma", "t2")
    c = paths.table_prefix("pwd", "other_dataset", "t1")
    d = paths.table_prefix("other_dept", "vishwakarma", "t1")
    assert len({a, b, c, d}) == 4
