import os
from pathlib import Path

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# data_services/.env, regardless of the directory a command is run from.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# OPENMETADATA_ENV value -> prefix of that server's two settings in .env
_SERVERS = {"local": "LOCAL", "development": "DEV"}


def load_env() -> str:
    """Load .env for every CLI entry point, then point OPENMETADATA_HOST_PORT/
    OPENMETADATA_JWT_TOKEN at the server OPENMETADATA_ENV picks:

        OPENMETADATA_ENV=local        -> LOCAL_OPENMETADATA_HOST_PORT / LOCAL_OPENMETADATA_JWT_TOKEN
        OPENMETADATA_ENV=development  -> DEV_OPENMETADATA_HOST_PORT / DEV_OPENMETADATA_JWT_TOKEN

    Both servers live side by side in the one .env file, so switching is a
    one-word edit (or `OPENMETADATA_ENV=local python3 -m ...` for one run).
    Variables already exported in the shell win over .env. Returns the
    environment used."""

    load_dotenv(_ENV_FILE)

    env = (os.environ.get("OPENMETADATA_ENV") or "local").strip().lower()
    if env not in _SERVERS:
        raise ValueError(f"OPENMETADATA_ENV={env!r} -- must be one of: {', '.join(_SERVERS)}")

    prefix = _SERVERS[env]
    for setting in ("OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN"):
        os.environ.setdefault(setting, os.environ.get(f"{prefix}_{setting}", ""))

    logger.info(f"Config: OPENMETADATA_ENV={env}, OpenMetadata={os.environ['OPENMETADATA_HOST_PORT'] or '(not set)'}")
    return env
