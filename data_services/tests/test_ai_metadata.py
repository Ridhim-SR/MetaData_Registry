import csv

from src.schema_registry import ai_metadata


def test_writes_metadata_csv_next_to_raw_file(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "t.txt"
    raw.write_text("sno integer NOT NULL, firm_name character varying(100), lat double precision")
    seen = {}

    def fake_draft(columns, definitions):
        seen["names"] = [c["name"] for c in columns]
        seen["definitions"] = definitions
        return {
            "columns": [{"name": "sno", "business_description": "Serial number", "tag": ""},
                        {"name": "lat", "business_description": "Latitude", "tag": "Geospatial"}],
            "dataset": {"description": "Works", "category": "CAT-3", "reason": "contractor data"},
        }

    monkeypatch.setattr(ai_metadata, "draft", fake_draft)
    defs = tmp_path / "cat.txt"
    defs.write_text("CAT-3: restricted")

    assert ai_metadata._main([str(raw), "--cat-definitions", str(defs)]) == 0

    rows = list(csv.DictReader(open(tmp_path / "t_metadata.csv")))
    assert [r["name"] for r in rows] == ["sno", "firm_name", "lat"]  # raw file's order
    assert rows[0]["business_description"] == "Serial number"
    assert rows[1]["business_description"] == ""  # a field the AI skipped stays blank
    assert rows[2]["tag"] == "Geospatial"
    assert seen["definitions"] == "CAT-3: restricted"
    out = capsys.readouterr().out
    assert "category:    CAT-3" in out and "catalog.yaml" in out
