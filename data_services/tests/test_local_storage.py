import os

import pytest

from src.storage.local import LocalObjectStorage


def test_transient_permission_error_on_replace_is_retried(tmp_path, monkeypatch):
    """Windows: os.replace() fails with PermissionError while an antivirus or
    search indexer briefly holds the destination open. That is transient, so
    the write must land on a retry instead of failing the whole run."""

    storage = LocalObjectStorage(tmp_path)
    real_replace, calls = os.replace, []

    def _flaky_replace(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError(13, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _flaky_replace)

    storage.write_bytes("x.csv", b"hello")

    assert len(calls) == 2
    assert storage.read_bytes("x.csv") == b"hello"


def test_a_persistent_permission_error_is_still_raised(tmp_path, monkeypatch):
    """Retrying must not turn a real denial into a silent success: after the
    attempts are used up the error propagates and no half-written file is
    left behind."""

    storage = LocalObjectStorage(tmp_path)

    def _denied(src, dst):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(os, "replace", _denied)
    monkeypatch.setattr("src.storage.local._REPLACE_DELAY", 0)

    with pytest.raises(PermissionError):
        storage.write_bytes("x.csv", b"hello")

    assert not storage.exists("x.csv")
    assert storage.list("") == []
