import csv
from pathlib import Path

from src.storage.base import ObjectStorage
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

    def write_csv(self, path: str, rows: list[dict]) -> None:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)

        # UTF-8 explicitly: dataset/table names and business descriptions are
        # routinely Devanagari, and the locale encoding on Windows is not.
        with full.open("w", newline="", encoding="utf-8") as f:
            if not rows:
                return
            # Union of every row's keys, in first-seen order: rows written by
            # older code may lack a field newer rows have (e.g. `deleted`),
            # and DictWriter would raise on a row containing an unlisted key.
            fieldnames = list(dict.fromkeys(key for row in rows for key in row))
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def read_csv(self, path: str) -> list[dict]:
        # utf-8-sig so a BOM (Excel's idea of "CSV") doesn't end up in the
        # first header name
        with self._full_path(path).open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def read_bytes(self, path: str) -> bytes:
        return self._full_path(path).read_bytes()

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
