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


@pytest.fixture
def confirm_env(monkeypatch):
    for key, value in {"ENVIRONMENT": "development", "WASABI_BUCKET": "bucket", "WASABI_PREFIX": "dev"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SDA_ASSUME_YES", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _changes_data(argv):
    cli.confirm_changes("change something")
    return 0


@pytest.mark.parametrize("answers, code", [
    (["yes", "development"], 0),   # both confirmations right -> runs
    (["no"], 1),                   # first answer no -> cancelled
    (["yes", "production"], 1),    # wrong environment name -> cancelled
])
def test_two_confirmations(confirm_env, monkeypatch, capsys, answers, code):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert cli.run_cli("sync", _changes_data, []) == code
    out = capsys.readouterr()
    assert "DEVELOPMENT" in out.out and "bucket/dev/" in out.out
    assert "\033[" not in out.out  # not a terminal -> no colour codes
    if code:
        assert "Cancelled -- nothing was changed." in out.err


def test_yes_flag_skips_the_questions(confirm_env, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("asked a question despite --yes"))
    assert cli.run_cli("sync", _changes_data, ["--yes"]) == 0
    assert "Confirmed with --yes." in capsys.readouterr().out


def test_no_terminal_and_no_yes_refuses(confirm_env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.run_cli("sync", _changes_data, []) == 1
    assert "needs a confirmation" in capsys.readouterr().err


def test_production_is_shown_in_red_on_a_terminal(confirm_env, monkeypatch, capsys):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    cli.run_cli("sync", _changes_data, ["--yes"])
    assert "\033[1;97;41m PRODUCTION \033[0m" in capsys.readouterr().out
