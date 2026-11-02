"""Local mirror for a SharePoint folder synchronized by OneDrive.

The configured folder must already be synced by the OneDrive desktop client.
OneDrive performs the upload; this module needs no Microsoft Graph access.
"""

import hashlib
import os
import tempfile
import threading
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SharePointConfigError(ValueError):
    pass


def _setting(name: str) -> str:
    from src.utils.config import ENVIRONMENTS

    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    prefix = ENVIRONMENTS.get(env, ("", ""))[0]
    if prefix:
        value = (os.environ.get(f"{prefix}_{name}") or "").strip()
        if value:
            return value
    return (os.environ.get(name) or "").strip()


class SharePointMirror:
    """Copy files into a local OneDrive-synchronized SharePoint folder."""

    def __init__(self, root_folder: str):
        if not root_folder:
            raise SharePointConfigError(
                "SHAREPOINT_LOCAL_MIRROR_FOLDER is required and must be "
                "the local folder synchronized with SharePoint"
            )
        self.root = Path(root_folder).expanduser().resolve()
        self._lock = threading.Lock()

    def upload_bytes(self, relative_path: str, data: bytes, mimetype: str = "text/csv",
                     skip_if_unchanged: bool = False, compare_latest: bool = False) -> str | None:
        del mimetype, compare_latest
        parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
        if not parts or any(part in (".", "..") for part in parts):
            raise ValueError("relative_path must be a safe relative file path")
        destination = (self.root.joinpath(*parts)).resolve()
        if self.root not in destination.parents:
            raise ValueError("relative_path must stay inside the SharePoint mirror folder")

        with self._lock:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if skip_if_unchanged and destination.is_file():
                if hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(data).digest():
                    logger.info(f"SharePoint: '{relative_path}' unchanged -- skipped")
                    return None
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as temporary:
                temporary.write(data)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        logger.info(f"SharePoint: copied '{relative_path}'")
        return str(destination)

    def upload_text(self, relative_path: str, text: str, mimetype: str = "text/plain",
                    skip_if_unchanged: bool = False) -> str | None:
        return self.upload_bytes(
            relative_path, text.encode("utf-8"), mimetype=mimetype,
            skip_if_unchanged=skip_if_unchanged,
        )


_cached_mirror: SharePointMirror | None = None
_cached_settings: str | None = None
_cached_lock = threading.Lock()


def reset_cache() -> None:
    global _cached_mirror, _cached_settings
    with _cached_lock:
        _cached_mirror = None
        _cached_settings = None


def mirror_from_env() -> SharePointMirror | None:
    global _cached_mirror, _cached_settings
    root_folder = _setting("SHAREPOINT_LOCAL_MIRROR_FOLDER")
    if not root_folder:
        return None
    with _cached_lock:
        if _cached_mirror is None or _cached_settings != root_folder:
            _cached_mirror = SharePointMirror(root_folder)
            _cached_settings = root_folder
        return _cached_mirror
