from unittest.mock import MagicMock, patch

from src.schema_registry.openmetadata import setup_custom_properties as scp


def _response(payload):
    r = MagicMock(ok=True)
    r.json.return_value = payload
    return r


def test_setup_adds_dataset_properties_and_the_table_json_property():
    def get(url, **kwargs):
        if url.endswith("/types/name/database"):
            return _response({"id": "db-type"})
        if url.endswith("/types/name/table"):
            return _response({"id": "table-type"})
        if "category=field" in url:
            return _response({"data": [{"id": "str-id", "name": "string"}]})
        return _response({"customProperties": []})

    with patch.object(scp.requests, "get", side_effect=get), patch.object(scp.requests, "patch") as patch_call:
        patch_call.return_value = _response({})
        scp.setup("http://om/api", "token")

    added = {(c.args[0].rsplit("/", 1)[1], c.kwargs["json"][0]["value"]["name"]) for c in patch_call.call_args_list}
    assert ("table-type", "extraMetadata") in added
    assert ("db-type", "datasetSteward") in added and ("db-type", "datasetOwner") in added
