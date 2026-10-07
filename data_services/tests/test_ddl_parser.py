import os

import pytest

from src.schema_registry.parsers.ddl_parser import parse_postgres_columns


def test_not_null_with_no_default():
    cols = parse_postgres_columns('sno integer NOT NULL')
    assert cols == [
        {"name": "sno", "data_type": "integer", "length": None, "scale": None, "nullable": False, "default": None}
    ]


def test_varchar_with_length_and_collate_and_not_null():
    cols = parse_postgres_columns(
        'division character varying(100) COLLATE pg_catalog."default" NOT NULL'
    )
    assert cols[0] == {
        "name": "division",
        "data_type": "character varying",
        "length": 100,
        "scale": None,
        "nullable": False,
        "default": None,
    }


def test_nullable_column_with_numeric_default():
    cols = parse_postgres_columns('cost1 double precision DEFAULT 0')
    assert cols[0] == {
        "name": "cost1",
        "data_type": "double precision",
        "length": None,
        "scale": None,
        "nullable": True,
        "default": "0",
    }


def test_multi_word_type_with_function_default():
    cols = parse_postgres_columns(
        "updated_main_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP"
    )
    assert cols[0] == {
        "name": "updated_main_at",
        "data_type": "timestamp without time zone",
        "length": None,
        "scale": None,
        "nullable": True,
        "default": "CURRENT_TIMESTAMP",
    }


def test_length_and_scale_numeric():
    cols = parse_postgres_columns("amount numeric(10,2) DEFAULT 0")
    assert cols[0]["length"] == 10
    assert cols[0]["scale"] == 2


def test_commas_inside_parens_do_not_split_columns():
    cols = parse_postgres_columns("a integer, amount numeric(10,2), b date")
    assert [c["name"] for c in cols] == ["a", "amount", "b"]


def test_multiple_columns_and_bare_type_no_length():
    cols = parse_postgres_columns("godate date, river integer DEFAULT 0")
    assert [c["name"] for c in cols] == ["godate", "river"]
    assert cols[0]["data_type"] == "date"
    assert cols[0]["length"] is None


@pytest.mark.skipif(not os.path.exists("samples/pwd_vishwakarma_full_raw_columns.txt"),
                    reason="real sample file is gitignored; not on this machine")
def test_real_vishwakarma_sample_parses_all_213_columns():
    ddl_text = open("samples/pwd_vishwakarma_full_raw_columns.txt").read()
    cols = parse_postgres_columns(ddl_text)
    assert len(cols) == 213
    names = {c["name"] for c in cols}
    assert {"firm_pannumber", "total_cost", "demand_status", "tender_date"} <= names


def test_pg_dump_default_before_not_null_is_not_nullable():
    """pg_dump always writes DEFAULT before NOT NULL -- the old end-of-line
    DEFAULT regex swallowed NOT NULL into the default and marked it nullable."""

    cols = parse_postgres_columns("id integer DEFAULT nextval('works_id_seq'::regclass) NOT NULL")
    assert cols[0]["nullable"] is False
    assert cols[0]["default"] == "nextval('works_id_seq'::regclass)"
    assert cols[0]["data_type"] == "integer"


def test_comma_inside_quoted_default_does_not_split_columns():
    cols = parse_postgres_columns("a text DEFAULT 'x, y', b integer")
    assert [c["name"] for c in cols] == ["a", "b"]
    assert cols[0]["default"] == "'x, y'"


def test_escaped_quote_inside_default():
    cols = parse_postgres_columns("a text DEFAULT 'it''s, here' NOT NULL, b integer")
    assert [c["name"] for c in cols] == ["a", "b"]
    assert cols[0]["default"] == "'it''s, here'"
    assert cols[0]["nullable"] is False


def test_quoted_identifier_with_space():
    cols = parse_postgres_columns('"Order Date" date NOT NULL')
    assert cols[0]["name"] == "Order Date"
    assert cols[0]["data_type"] == "date"
    assert cols[0]["nullable"] is False


def test_default_null_and_cast_default():
    cols = parse_postgres_columns(
        "a character varying(20) DEFAULT NULL::character varying, b text DEFAULT NULL"
    )
    assert cols[0]["default"] == "NULL::character varying"
    assert cols[0]["data_type"] == "character varying"
    assert cols[0]["length"] == 20
    assert cols[1]["default"] == "NULL"


def test_timestamp_precision_keeps_type_name_clean():
    cols = parse_postgres_columns("created timestamp(6) without time zone DEFAULT now() NOT NULL")
    assert cols[0]["data_type"] == "timestamp without time zone"
    assert cols[0]["length"] == 6
    assert cols[0]["default"] == "now()"
    assert cols[0]["nullable"] is False


def test_inline_constraints_are_not_part_of_type_or_default():
    cols = parse_postgres_columns(
        "id integer CONSTRAINT works_pk PRIMARY KEY, "
        "dept_id integer NOT NULL REFERENCES departments(id), "
        "qty integer DEFAULT 0 CHECK (qty >= 0)"
    )
    assert [(c["name"], c["data_type"], c["nullable"], c["default"]) for c in cols] == [
        ("id", "integer", False, None),
        ("dept_id", "integer", False, None),
        ("qty", "integer", True, "0"),
    ]


def test_full_create_table_statement_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="full CREATE TABLE statement"):
        parse_postgres_columns("CREATE TABLE works (id integer, CONSTRAINT pk PRIMARY KEY (id));")


def test_table_level_constraint_line_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="table-level constraint"):
        parse_postgres_columns("id integer NOT NULL, CONSTRAINT works_pk PRIMARY KEY (id)")


def test_trailing_semicolon_is_ignored():
    cols = parse_postgres_columns("a integer, b date;")
    assert [c["data_type"] for c in cols] == ["integer", "date"]
