import csv
import os
import tempfile
from pathlib import Path

from filelock import FileLock

from src.storage.base import ObjectStorage, rows_to_csv
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LocalObjectStorage(ObjectStorage):
    """Filesystem-backed ObjectStorage, rooted at `root_dir`.

    Swap for an S3/Wasabi-backed implementation later; callers only ever
    deal in relative paths like `pwd/vishwakarma/raw/schemas/<ts>.csv`.
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)
        logger.info(f"LocalObjectStorage ready: root={self.root.resolve()}")

    def _full_path(self, path: str) -> Path:
        return self.root / path

    def _atomic_write(self, path: str, data: bytes) -> None:
        """Write to a temp file in the same folder, then swap it into place
        with os.replace (atomic on one filesystem). Opening the target with
        "w" empties it first, so a crash mid-write used to leave a truncated
        _lookups/*.csv -- i.e. a wiped registry."""

        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=full.parent, prefix=f".{full.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, full)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def write_csv(self, path: str, rows: list[dict]) -> None:
        self._atomic_write(path, rows_to_csv(rows).encode("utf-8"))

    def write_bytes(self, path: str, data: bytes) -> None:
        self._atomic_write(path, data)

    def read_bytes(self, path: str) -> bytes:
        return self._full_path(path).read_bytes()

    def read_csv(self, path: str) -> list[dict]:
        # utf-8-sig so a BOM (Excel's idea of "CSV") doesn't end up in the
        # first header name
        with self._full_path(path).open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    def list(self, prefix: str) -> list[str]:
        base = self._full_path(prefix)
        if not base.exists():
            return []
        return sorted(
            str(p.relative_to(self.root))
            for p in base.rglob("*")
            if p.is_file()
        )

    def lock_path(self, path: str) -> str:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        return str(full) + ".lock"

    def lock(self, path: str) -> FileLock:
        # Local storage is only ever shared by processes on this machine,
        # which an OS file lock covers.
        return FileLock(self.lock_path(path))
