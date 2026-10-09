import pytest

from src.utils import cli, logger as log_module


@pytest.fixture(autouse=True)
def logs_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(log_module, "LOG_DIR", tmp_path / "logs")
    yield
    log_module._file_handler = None


def _only_log(tmp_path):
    (path,) = (tmp_path / "logs").glob("*.log")
    return path.read_text()


def test_expected_problem_prints_a_box_not_a_traceback(tmp_path, capsys):
    def main(argv):
        raise PermissionError("ENVIRONMENT=production isn't allowed on branch 'x' -- run it on main")

    assert cli.run_cli("sync", main, []) == 1
    err = capsys.readouterr().err
    assert "ERROR: ENVIRONMENT=production isn't allowed on branch 'x'" in err
    assert "What to do: run it on main" in err
    assert "Traceback" not in err
    assert "Traceback" in _only_log(tmp_path)  # full details kept for whoever investigates


def test_unexpected_problem_points_to_the_log(tmp_path, capsys):
    def main(argv):
        raise ZeroDivisionError("boom")

    assert cli.run_cli("sync", main, []) == 1
    err = capsys.readouterr().err
    assert "something unexpected went wrong (ZeroDivisionError: boom)" in err
    assert "send the log file below" in err and "Traceback" not in err


def test_missing_setting_is_named(capsys):
    def main(argv):
        import os
        return os.environ["SOME_MISSING_SETTING_XYZ"]

    assert cli.run_cli("pipeline", main, []) == 1
    assert "Missing setting SOME_MISSING_SETTING_XYZ" in capsys.readouterr().err


def test_unreachable_server_message(capsys):
    import requests

    def main(argv):
        raise requests.exceptions.ConnectionError("down")

    assert cli.run_cli("sync", main, []) == 1
    assert "Can't reach the OpenMetadata server" in capsys.readouterr().err


def test_success_returns_the_command_exit_code_and_writes_a_log(tmp_path):
    assert cli.run_cli("sync", lambda argv: 0, []) == 0
    assert cli.run_cli("sync", lambda argv: 3, []) == 3
    assert len(list((tmp_path / "logs").glob("sync_*.log"))) >= 1


def test_help_writes_no_log_file(tmp_path):
    assert cli.run_cli("sync", lambda argv: 0, ["--help"]) == 0
    assert not (tmp_path / "logs").exists()


def test_missing_wasabi_permission_names_it(capsys):
    from botocore.exceptions import ClientError

    def main(argv):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "User: x is not authorized to perform: s3:CreateBucket"}},
                          "CreateBucket")

    assert cli.run_cli("backup", main, []) == 1
    err = capsys.readouterr().err
    assert "not authorized to perform: s3:CreateBucket" in err and "Wasabi admin" in err
