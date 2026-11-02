"""Optional Google Drive mirror for the curated schema output.

The Wasabi bucket stays the source of truth; this only copies a
deliberately small subset to Google Drive so non-technical stakeholders can
read it:

    department/<department_id>/<dataset_slug>/<table_slug>/curated/schemas/<ts>.csv
    department/<department_id>/<dataset_slug>/dataset_details.txt

Nothing is mirrored when GOOGLE_DRIVE_FOLDER_ID is blank, so local and CI
runs keep working with no Drive account at all.

Authentication is a Google service account: share the destination Drive
folder with the service account's e-mail address (Viewer is not enough --
it needs Editor), then point GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE at its JSON
key (or set GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON to the JSON itself).

Every environment can point at its own folder with the usual prefix, e.g.
DEV_GOOGLE_DRIVE_FOLDER_ID / PROD_GOOGLE_DRIVE_FOLDER_ID (see
src/utils/config.py). The unscoped GOOGLE_DRIVE_* value is the fallback.
"""

import hashlib
import io
import json
import os
import threading

from src.utils.logger import get_logger

logger = get_logger(__name__)

SCOPES = ("https://www.googleapis.com/auth/drive",)
_FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveConfigError(ValueError):
    pass


def _setting(name: str) -> str:
    """Prefixed setting for the current ENVIRONMENT, else the unscoped one.

    ENVIRONMENT is set by config.load_env(); when this module is used
    without it, the unscoped GOOGLE_DRIVE_* value still applies."""

    from src.utils.config import ENVIRONMENTS

    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    prefix = ENVIRONMENTS.get(env, ("", ""))[0]
    if prefix:
        value = (os.environ.get(f"{prefix}_{name}") or "").strip()
        if value:
            return value
    return (os.environ.get(name) or "").strip()


def folder_id_from_env() -> str:
    return _setting("GOOGLE_DRIVE_FOLDER_ID")


def _credentials_from_env():
    """(file path, info dict) from the environment -- exactly one or neither."""

    account_json = _setting("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
    account_file = _setting("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE")
    if account_json:
        try:
            return None, json.loads(account_json)
        except json.JSONDecodeError as exc:
            raise GoogleDriveConfigError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is not valid JSON "
                f"({exc}); paste the whole service-account key, or use "
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE instead"
            ) from exc
    return account_file or None, None


class GoogleDriveMirror:
    """Upload a small set of files into one Drive folder tree.

    The Drive API allows duplicate names, so an upload first looks for a
    file with that name in the target folder and updates it in place;
    otherwise it creates one. That makes re-running a sync idempotent
    instead of littering the folder with copies.

    Folder lookups are cached for the lifetime of the instance, and all
    Drive mutations are serialized by a lock: sync ingests tables in a
    thread pool, and two threads creating the same department/dataset folder
    at once would otherwise make duplicates.
    """

    def __init__(self, folder_id: str, service_account_file: str | None = None,
                 service_account_info: dict | None = None, scopes=SCOPES):
        if not folder_id:
            raise GoogleDriveConfigError("A Google Drive folder id is required")
        if service_account_file and service_account_info:
            raise GoogleDriveConfigError(
                "Set only one of GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE / "
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"
            )
        self.folder_id = folder_id
        self.service_account_file = service_account_file
        self.service_account_info = service_account_info
        self.scopes = list(scopes)
        self._service = None
        self._folder_cache: dict[tuple[str, ...], str] = {(): folder_id}
        self._lock = threading.Lock()

    def _build_service(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise GoogleDriveConfigError(
                "Google Drive mirroring needs google-api-python-client and "
                "google-auth -- install requirements.txt (or pip install "
                "google-api-python-client google-auth)"
            ) from exc

        if self.service_account_info:
            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_info, scopes=self.scopes
            )
        elif self.service_account_file:
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file, scopes=self.scopes
            )
        else:
            import google.auth

            credentials, _ = google.auth.default(scopes=self.scopes)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    @property
    def service(self):
        if self._service is None:
            self._service = self._build_service()
        return self._service

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _md5(data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _list_children(self, name: str, parent_id: str, mime_type: str | None = None) -> list[dict]:
        query = f"name = '{self._escape(name)}' and '{parent_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        response = self.service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, md5Checksum)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        return response.get("files", [])

    def _latest_file(self, parent_id: str) -> dict | None:
        """Newest non-folder file in a folder, by name (our snapshot names are
        fixed-width timestamps, so name order == chronological order)."""

        response = self.service.files().list(
            q=f"'{parent_id}' in parents and trashed = false and mimeType != '{_FOLDER_MIME}'",
            spaces="drive",
            fields="files(id, name, md5Checksum)",
            orderBy="name desc",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = response.get("files", [])
        return files[0] if files else None

    def _ensure_folder(self, name: str, parent_id: str) -> str:
        existing = self._list_children(name, parent_id, _FOLDER_MIME)
        if existing:
            return existing[0]["id"]
        created = self.service.files().create(
            body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
            fields="id",
            supportsAllDrives=True,
        ).execute()
        logger.info(f"Google Drive: created folder '{name}'")
        return created["id"]

    def _parent_for(self, folders: tuple[str, ...]) -> str:
        parent = self._folder_cache[()]
        for index, name in enumerate(folders):
            key = folders[: index + 1]
            if key in self._folder_cache:
                parent = self._folder_cache[key]
                continue
            parent = self._ensure_folder(name, parent)
            self._folder_cache[key] = parent
        return parent

    def upload_bytes(self, relative_path: str, data: bytes, mimetype: str = "text/csv",
                     skip_if_unchanged: bool = False, compare_latest: bool = False) -> str | None:
        """Write `data` to `relative_path` under the configured root folder.

        Idempotent by design:
          * a file with the same name is updated in place, never duplicated;
          * `skip_if_unchanged` compares the MD5 Drive reports for that file
            and does nothing when the content is identical;
          * `compare_latest` compares against the newest file already in the
            folder -- used for timestamped snapshots, so re-running an
            unchanged ingest does not add a second identical CSV.

        Returns the Drive file id, or None when the upload was skipped."""

        from googleapiclient.http import MediaIoBaseUpload

        parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
        if not parts:
            raise ValueError("relative_path must name a file")
        filename, folders = parts[-1], tuple(parts[:-1])
        digest = self._md5(data)

        with self._lock:
            parent_id = self._parent_for(folders)

            if compare_latest:
                latest = self._latest_file(parent_id)
                if latest and latest.get("md5Checksum") == digest:
                    logger.info(
                        f"Google Drive: '{relative_path}' unchanged since "
                        f"'{latest.get('name')}' -- skipped"
                    )
                    return None

            existing = self._list_children(filename, parent_id)
            if existing:
                file_id = existing[0]["id"]
                if skip_if_unchanged and existing[0].get("md5Checksum") == digest:
                    logger.info(f"Google Drive: '{relative_path}' unchanged -- skipped")
                    return None
                media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)
                self.service.files().update(
                    fileId=file_id, media_body=media, supportsAllDrives=True
                ).execute()
                action = "updated"
            else:
                media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)
                file_id = self.service.files().create(
                    body={"name": filename, "parents": [parent_id]},
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()["id"]
                action = "created"
        logger.info(f"Google Drive: {action} '{relative_path}'")
        return file_id

    def upload_text(self, relative_path: str, text: str, mimetype: str = "text/plain",
                    skip_if_unchanged: bool = False) -> str | None:
        return self.upload_bytes(
            relative_path, text.encode("utf-8"), mimetype=mimetype,
            skip_if_unchanged=skip_if_unchanged,
        )


_cached_mirror: GoogleDriveMirror | None = None
_cached_settings: tuple | None = None
_cached_lock = threading.Lock()


def reset_cache() -> None:
    """Drop the process-wide client (tests, or after changing .env)."""

    global _cached_mirror, _cached_settings
    with _cached_lock:
        _cached_mirror = None
        _cached_settings = None


def mirror_from_env() -> GoogleDriveMirror | None:
    """The configured mirror, or None when Drive mirroring is switched off.

    Returns None without touching the network when GOOGLE_DRIVE_FOLDER_ID is
    blank, so this is safe to call from every pipeline run. Raises
    GoogleDriveConfigError only when a folder id is set but the credentials
    are missing/invalid -- that is a configuration mistake worth surfacing,
    not something to silently skip."""

    global _cached_mirror, _cached_settings

    folder_id = folder_id_from_env()
    if not folder_id:
        return None
    account_file, account_info = _credentials_from_env()
    settings = (folder_id, account_file, json.dumps(account_info, sort_keys=True) if account_info else "")

    with _cached_lock:
        if _cached_mirror is not None and _cached_settings == settings:
            return _cached_mirror
        if not account_file and not account_info:
            raise GoogleDriveConfigError(
                "GOOGLE_DRIVE_FOLDER_ID is set, but no service account is configured -- "
                "set GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE (path to the JSON key) or "
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"
            )
        mirror = GoogleDriveMirror(folder_id, service_account_file=account_file,
                                   service_account_info=account_info)
        _cached_mirror = mirror
        _cached_settings = settings
        return mirror
