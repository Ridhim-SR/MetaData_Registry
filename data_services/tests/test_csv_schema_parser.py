import pytest

from src.schema_registry.csv_schema_parser import parse_csv_columns


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_verbose_headers_get_normalized(tmp_path):
    path = _write(
        tmp_path,
        "dept_a.csv",
        "Field Name,Data Type,Max Length,Is Nullable,Default Value\n"
        "budget_id,integer,,No,\n"
        "project_name,varchar,255,Yes,\n",
    )
    cols = parse_csv_columns(path)
    assert cols[0] == {
        "name": "budget_id",
        "data_type": "integer",
        "length": None,
        "scale": None,
        "nullable": False,
        "default": None,
    }
    assert cols[1]["length"] == 255
    assert cols[1]["nullable"] is True


def test_minimal_headers_default_sensibly(tmp_path):
    path = _write(tmp_path, "dept_b.csv", "column,type\nregion_code,varchar\namount,numeric\n")
    cols = parse_csv_columns(path)
    assert cols == [
        {"name": "region_code", "data_type": "varchar", "length": None, "scale": None, "nullable": True, "default": None},
        {"name": "amount", "data_type": "numeric", "length": None, "scale": None, "nullable": True, "default": None},
    ]


def test_missing_required_fields_raises(tmp_path):
    path = _write(tmp_path, "dept_c_bad.csv", "Description,Category\nsome text,finance\n")
    with pytest.raises(ValueError, match="missing required field"):
        parse_csv_columns(path)


def test_required_column_is_not_silently_aliased_to_nullable(tmp_path):
    """`required` is the inverse of `nullable` -- must not be auto-mapped,
    since a wrong guess here would flip meaning, not just be imprecise."""

    path = _write(tmp_path, "dept_d.csv", "Column,Type,Required\npatient_id,integer,Yes\n")
    cols = parse_csv_columns(path)
    assert cols[0]["nullable"] is True
