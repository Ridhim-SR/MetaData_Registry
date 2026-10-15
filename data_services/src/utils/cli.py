"""How every command line tool ends: with a plain message, never a raw
Python traceback.

    if __name__ == "__main__":
        sys.exit(run_cli("sync", _main, sys.argv[1:]))

- Expected problems (wrong branch, catalog mistake, missing file, rejected
  schema, lock held, server unreachable, expired token, ...) print a short
  box: what went wrong and what to do.
- Anything unexpected prints one line; the full technical details go to
  the run's log file.
- Every run writes logs/<command>_<time>.log, so it can be shared.
- A command that changes data calls confirm_changes() first: it shows where
  it will write and asks twice (--yes skips the questions).
"""

import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from src.utils.logger import get_logger, start_log_file

logger = get_logger(__name__)

_LINE = "-" * 78


# ANSI colours, only for a real terminal (log files and scripts stay plain;
# NO_COLOR=1 turns them off). Production is red so it can't be missed.
_ENV_COLOURS = {"local": "1;32", "development": "1;33", "production": "1;97;41"}


def _paint(text: str, code: str, stream=None) -> str:
    if os.environ.get("NO_COLOR") or not (stream or sys.stdout).isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _paint_box(lines: list[str], stream) -> str:
    """The error box with ERROR in red and the hint in bold."""

    styles = {"ERROR:": "1;31", "What to do:": "1", "Log file:": "2"}
    return "\n".join(
        next((_paint(line, code, stream) for start, code in styles.items() if line.startswith(start)), line)
        for line in lines
    )


class Cancelled(Exception):
    """The person answered no at a confirmation -- nothing was changed."""


def confirm_changes(action: str) -> None:
    """Before a command changes data in Wasabi or OpenMetadata: show where it
    will write, then ask twice (yes, then the environment's name). --yes on
    the command line skips the questions (for scripts); with no terminal to
    ask in and no --yes, the command refuses rather than guess."""

    from src.utils.config import _current_branch

    env = os.environ.get("ENVIRONMENT", "?")
    target = f"{os.environ.get('WASABI_BUCKET', '?')}/{os.environ.get('WASABI_PREFIX', '')}/"
    if os.environ.get("WASABI_BACKUP_BUCKET"):
        target += f"   (backup: {os.environ['WASABI_BACKUP_BUCKET']})"
    publishes = os.environ.get("OPENMETADATA_HOST_PORT") if os.environ.get("OPENMETADATA_JWT_TOKEN") else None
    env_colour = _ENV_COLOURS.get(env, "1")
    rule = _paint(_LINE, env_colour)
    print("\n".join([
        rule,
        f"{_paint('About to:', '1')}      {_paint(action, '1')}",
        f"{_paint('Environment:', '1')}   {_paint(f' {env.upper()} ', env_colour)}   (git branch: {_current_branch() or 'unknown'})",
        f"{_paint('Wasabi:', '1')}        {target}",
        f"{_paint('OpenMetadata:', '1')}  {publishes or _paint('(no token -- nothing will be published)', '2')}",
        rule,
    ]), flush=True)
    if os.environ.get("SDA_ASSUME_YES") == "1":
        print(_paint("Confirmed with --yes.", "32"))
        return
    if not sys.stdin.isatty():
        raise PermissionError("This command changes data and needs a confirmation -- "
                              "run it in a terminal, or add --yes if you're sure")
    if input(_paint("Continue? Type yes: ", "1;36")).strip().lower() != "yes":
        raise Cancelled()
    if input(_paint(f"Confirm again -- type the environment name ({env}): ", "1;36")).strip().lower() != env:
        raise Cancelled()


def _explain(exc: BaseException) -> tuple[str, str] | None:
    """(what went wrong, what to do) for problems we expect, else None."""

    import requests
    from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

    message = str(exc).strip()
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) \
            or type(exc).__name__ == "RestTransportError":  # the OpenMetadata SDK's own "can't connect"
        return (f"Can't reach the OpenMetadata server ({os.environ.get('OPENMETADATA_HOST_PORT', '?')}).",
                "Check OPENMETADATA_HOST_PORT for this ENVIRONMENT in .env. For BIPP2 (development) you need the "
                "office network or VPN; for local, start it: cd ../infrastructure/openmetadata && docker compose up -d")
    if isinstance(exc, (EndpointConnectionError, NoCredentialsError)):
        return (f"Can't reach Wasabi: {message}", "Check your internet connection and the WASABI_* settings in .env.")
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "?")
        reason = exc.response.get("Error", {}).get("Message", "")
        if code == "AccessDenied" and "not authorized" in reason:  # keys work, the permission is missing
            return (f"Wasabi refused the request: {reason}",
                    "Ask your Wasabi admin for that permission, or to run this step with their key.")
        return (f"Wasabi refused the request ({code}).",
                "Check WASABI_ACCESS_KEY_ID / WASABI_SECRET_ACCESS_KEY / WASABI_BUCKET in .env."
                if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied", "NoSuchBucket", "403")
                else message)
    status = getattr(getattr(exc, "response", None), "status_code", None) if isinstance(exc, requests.exceptions.HTTPError) \
        else getattr(exc, "status_code", None) if type(exc).__name__ == "APIError" else None
    if status == 401:
        return ("OpenMetadata says the token is not valid (401).",
                "Get a new token (Settings -> Bots -> ingestion-bot) and put it in .env for this ENVIRONMENT.")
    if isinstance(exc, KeyError) and isinstance(exc.args[0] if exc.args else None, str) and exc.args[0].isupper():
        return (f"Missing setting {exc.args[0]}.", f"Add {exc.args[0]}=... to .env, or put it in front of the command.")
    if isinstance(exc, (PermissionError, ValueError, FileNotFoundError, TimeoutError)):
        # our own messages are written as "<what went wrong> -- <what to do>"
        problem, _, fix = message.partition(" -- ")
        return problem, fix
    return None


def run_cli(command: str, main: Callable[[list[str]], int | None], argv: list[str]) -> int:
    """Run `main(argv)`, logging to a file, and turn any failure into a
    readable message and a non-zero exit code."""

    if argv[:1] in (["-h"], ["--help"]):
        return main(argv) or 0  # help needs no log file
    if "--yes" in argv:  # answers confirm_changes() for this run
        argv = [a for a in argv if a != "--yes"]
        os.environ["SDA_ASSUME_YES"] = "1"

    log_path = start_log_file(command)
    try:
        log_path = log_path.relative_to(Path.cwd())  # shorter to read: logs/sync_....log
    except ValueError:
        pass
    try:
        code = main(argv) or 0
        logger.info(f"Finished ({'ok' if code == 0 else f'exit code {code}'}). Log: {log_path}")
        return code
    except (KeyboardInterrupt, EOFError):
        print(f"\nStopped by you. Log: {log_path}", file=sys.stderr)
        return 130
    except Cancelled:
        print(_paint("Cancelled -- nothing was changed.", "1;33", sys.stderr), file=sys.stderr)
        logger.info("Cancelled at the confirmation; nothing was changed.")
        return 1
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- the whole point: no raw tracebacks for users
        explained = _explain(exc)
        lines = [_LINE]
        if explained:
            problem, fix = explained
            lines.append(f"ERROR: {problem}")
            if fix:
                lines.append(f"What to do: {fix}")
        else:
            lines.append(f"ERROR: something unexpected went wrong ({type(exc).__name__}: {exc})")
            lines.append("What to do: send the log file below to the team -- it has the full technical details.")
        lines += [f"Log file: {log_path}", _LINE]
        print("\n" + _paint_box(lines, sys.stderr), file=sys.stderr)
        with open(log_path, "a", encoding="utf-8") as f:  # the same message + full details for whoever investigates
            f.write("\n" + "\n".join(lines) + "\n\nTechnical details:\n" + "".join(traceback.format_exception(exc)))
        return 1
