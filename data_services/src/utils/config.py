import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# data_services/.env, regardless of the directory a command is run from.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# ENVIRONMENT value -> (prefix of its OpenMetadata settings in .env,
#                        its folder in the Wasabi bucket)
ENVIRONMENTS = {
    "local": ("LOCAL", "local"),
    "development": ("DEV", "dev"),
    "production": ("PROD", "prod"),
}

# Wasabi settings an environment can set for itself with its prefix (e.g.
# LOCAL_WASABI_BUCKET); unset ones fall back to the shared WASABI_... value.
_WASABI_SETTINGS = (
    "WASABI_BUCKET", "WASABI_ENDPOINT_URL", "WASABI_REGION", "WASABI_ACCESS_KEY_ID",
    "WASABI_SECRET_ACCESS_KEY", "WASABI_BACKUP_BUCKET", "WASABI_BACKUP_REGION",
)
# local must bring its own account: these can't fall back to the company one.
_LOCAL_REQUIRED = ("WASABI_BUCKET", "WASABI_ENDPOINT_URL", "WASABI_ACCESS_KEY_ID", "WASABI_SECRET_ACCESS_KEY")

# Each git branch runs exactly one ENVIRONMENT, so shared data only ever
# comes from reviewed code: the production branch -> production, main ->
# development, any other branch (or an unknown one) -> local.
PRODUCTION_BRANCH = "production"
MAIN_BRANCH = "main"


def environment_for_branch(branch: str | None) -> str:
    return {PRODUCTION_BRANCH: "production", MAIN_BRANCH: "development"}.get(branch, "local")


def _current_branch() -> str | None:
    """The checked-out git branch of this repo, or None if it can't be told
    (no git, not a checkout, or a detached HEAD)."""

    try:
        branch = subprocess.run(
            ["git", "-C", str(_ENV_FILE.parent), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None if branch in ("", "HEAD") else branch


def check_branch_allows(env: str, branch: str | None) -> None:
    """Refuse an ENVIRONMENT that isn't this branch's one."""

    expected = environment_for_branch(branch)
    if env == expected:
        return
    where = f"branch '{branch}'" if branch else "an unknown git branch"
    if env == "production":
        hint = f"production only runs on the '{PRODUCTION_BRANCH}' branch: merge {MAIN_BRANCH} into it, check it out, then run it there."
    elif env == "development":
        hint = f"development only runs on '{MAIN_BRANCH}': merge your PR, then git checkout {MAIN_BRANCH} && git pull."
    else:
        hint = f"on this branch use ENVIRONMENT={expected} (or leave ENVIRONMENT blank)."
    raise PermissionError(f"ENVIRONMENT={env} isn't allowed on {where} (it runs {expected}) -- {hint}")


def load_env() -> str:
    """Load .env for every CLI entry point, then apply the one switch that
    says where this run reads and writes. Each git branch has one:

        other branches -> local        Wasabi local/ folder, LOCAL_OPENMETADATA_*
        main           -> development  Wasabi dev/ folder,   DEV_OPENMETADATA_*
        production     -> production   Wasabi prod/ folder,  PROD_OPENMETADATA_*

    ENVIRONMENT blank = the branch's one; any other value is refused
    (check_branch_allows). main and production use the company Wasabi
    (WASABI_...); local uses only LOCAL_WASABI_... (your own account) and
    stops if those are blank, so a feature branch never touches company
    data. Variables
    already exported in the shell win over .env. Returns the environment used."""

    load_dotenv(_ENV_FILE)

    branch = _current_branch()
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower() or environment_for_branch(branch)
    if env not in ENVIRONMENTS:
        raise ValueError(f"ENVIRONMENT={env!r} -- must be one of: {', '.join(ENVIRONMENTS)}")
    check_branch_allows(env, branch)
    os.environ["ENVIRONMENT"] = env

    prefix, wasabi_folder = ENVIRONMENTS[env]
    for setting in ("OPENMETADATA_HOST_PORT", "OPENMETADATA_JWT_TOKEN"):
        os.environ.setdefault(setting, os.environ.get(f"{prefix}_{setting}", ""))
    for setting in _WASABI_SETTINGS:
        own = os.environ.get(f"{prefix}_{setting}", "")
        if env == "local" or own:  # local only ever uses its own account, never the company one
            os.environ[setting] = own

    if env == "local":
        missing = [f"LOCAL_{s}" for s in _LOCAL_REQUIRED if not os.environ.get(s)]
        if missing:
            raise ValueError(
                f"Feature branches use your own Wasabi account, but {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} blank in .env -- fill in section 3b "
                f"(the company Wasabi is only for main and production)"
            )
    elif not os.environ.get("WASABI_BUCKET"):
        raise ValueError(
            f"ENVIRONMENT={env} stores data in Wasabi, but WASABI_BUCKET is blank in .env -- fill it in "
            f"(see .env.example)"
        )
    os.environ.setdefault("WASABI_PREFIX", wasabi_folder)

    logger.info(
        f"Config: ENVIRONMENT={env} | branch: {branch or 'unknown'} | "
        f"storage: Wasabi {os.environ['WASABI_BUCKET']}/{os.environ['WASABI_PREFIX']}/ | "
        f"OpenMetadata: {os.environ['OPENMETADATA_HOST_PORT'] or '(not set)'}"
    )
    return env
