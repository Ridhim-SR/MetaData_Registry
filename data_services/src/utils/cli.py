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
"""

import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from src.utils.logger import get_logger, start_log_file

logger = get_logger(__name__)

_LINE = "-" * 78


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

    log_path = start_log_file(command)
    try:
        log_path = log_path.relative_to(Path.cwd())  # shorter to read: logs/sync_....log
    except ValueError:
        pass
    try:
        code = main(argv) or 0
        logger.info(f"Finished ({'ok' if code == 0 else f'exit code {code}'}). Log: {log_path}")
        return code
    except KeyboardInterrupt:
        print(f"\nStopped by you (Ctrl+C). Log: {log_path}", file=sys.stderr)
        return 130
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
        print("\n" + "\n".join(lines), file=sys.stderr)
        with open(log_path, "a", encoding="utf-8") as f:  # the same message + full details for whoever investigates
            f.write("\n" + "\n".join(lines) + "\n\nTechnical details:\n" + "".join(traceback.format_exception(exc)))
        return 1
