import os
from pathlib import Path

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# data_services/.env, regardless of the directory a command is run from.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# ENVIRONMENT value -> (prefix of its OpenMetadata settings in .env,
#                        Wasabi folder, or None = local storage/ folder)
ENVIRONMENTS = {
    "local": ("LOCAL", None),
    "development": ("DEV", "dev"),
    "production": ("PROD", "prod"),
}


def load_env() -> str:
    """Load .env for every CLI entry point, then apply the one switch that
    says where this run reads and writes:

        ENVIRONMENT=local        -> storage/ folder on this machine, LOCAL_OPENMETADATA_*
        ENVIRONMENT=development  -> Wasabi bucket, dev/ folder,      DEV_OPENMETADATA_*
        ENVIRONMENT=production   -> Wasabi bucket, prod/ folder,     PROD_OPENMETADATA_*

    `local` never touches Wasabi, even if WASABI_BUCKET is filled in, so
    trying things out can't change shared data. `development`/`production`
    refuse to run without WASABI_BUCKET rather than silently writing to
    this machine's disk. Variables already exported in the shell win over
    .env (e.g. `ENVIRONMENT=local python3 -m ...` for one run). Returns the
    environment used."""

    load_dotenv(_ENV_FILE)

    env = (os.environ.get("ENVIRONMENT") or "local").strip().lower()
    if env not in ENVIRONMENTS:
        raise ValueError(f"ENVIRONMENT={env!r} -- must be one of: {', '.join(ENVIRONMENTS)}")
    os.environ["ENVIRONMENT"] = env

    prefix, wasabi_folder = ENVIRONMENTS[env]
    for setting in ("OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN"):
        os.environ.setdefault(setting, os.environ.get(f"{prefix}_{setting}", ""))

    if wasabi_folder is None:
        os.environ["WASABI_BUCKET"] = ""  # storage_from_env() -> local storage/ folder
    else:
        if not os.environ.get("WASABI_BUCKET"):
            raise ValueError(
                f"ENVIRONMENT={env} stores data in Wasabi, but WASABI_BUCKET is blank in .env. "
                f"Fill it in, or use ENVIRONMENT=local to work on this machine only."
            )
        os.environ.setdefault("WASABI_PREFIX", wasabi_folder)

    storage = (
        f"Wasabi {os.environ['WASABI_BUCKET']}/{os.environ['WASABI_PREFIX']}/"
        if wasabi_folder else f"local folder {os.environ.get('STORAGE_ROOT', 'storage')}/"
    )
    logger.info(
        f"Config: ENVIRONMENT={env} | storage: {storage} | "
        f"OpenMetadata: {os.environ['OPENMETADATA_HOST_PORT'] or '(not set)'}"
    )
    return env
