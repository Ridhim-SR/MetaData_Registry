from src.schema_registry.ddl_parser import parse_postgres_columns


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


def test_real_vishwakarma_sample_parses_all_213_columns():
    ddl_text = open("samples/pwd_vishwakarma_full_raw_columns.txt").read()
    cols = parse_postgres_columns(ddl_text)
    assert len(cols) == 213
    names = {c["name"] for c in cols}
    assert {"firm_pannumber", "total_cost", "demand_status", "tender_date"} <= names
