import csv
from pathlib import Path

from src.storage.base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    """Filesystem-backed ObjectStorage, rooted at `root_dir`.

    Swap for an S3/Wasabi-backed implementation later; callers only ever
    deal in relative paths like `pwd/vishwakarma/raw/schemas/<ts>.csv`.
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)

    def _full_path(self, path: str) -> Path:
        return self.root / path

    def write_csv(self, path: str, rows: list[dict]) -> None:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)

        with full.open("w", newline="") as f:
            if not rows:
                return
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def read_csv(self, path: str) -> list[dict]:
        with self._full_path(path).open(newline="") as f:
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
