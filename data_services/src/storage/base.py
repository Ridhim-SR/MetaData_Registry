import csv
import io
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


def rows_to_csv(rows: list[dict]) -> str:
    """Serialize rows as CSV text. The header is every key from every row,
    in first-seen order -- not just the first row's keys -- so a lookup file
    written before a field existed (e.g. datasets.csv before
    `dataset_description`) can take a new row that has it, with older rows
    left blank in that column instead of DictWriter raising."""

    if not rows:
        return ""
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


class ObjectStorage(ABC):
    """Storage backend for department schema metadata.

    Paths are always relative and shaped like:
        <department>/<dataset>/<raw|curated>/schemas/<filename>
    so the same interface can back a local filesystem now and an
    S3-compatible bucket (e.g. Wasabi) later without changing callers.

    Rows are plain dicts (one per field), written/read as CSV so the
    output can be opened directly in a spreadsheet for review.
    """

    @abstractmethod
    def write_csv(self, path: str, rows: list[dict]) -> None:
        ...

    @abstractmethod
    def read_csv(self, path: str) -> list[dict]:
        ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """Store opaque bytes verbatim (the department's original submission,
        a SHA-256 sidecar, ...). CSV-only storage can't hold these: the point
        of keeping the original file is that it survives a parser bug, so it
        must be written exactly as it arrived, never re-serialized."""
        ...

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        ...

    @abstractmethod
    def list(self, prefix: str) -> list[str]:
        ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """Store a file exactly as given -- e.g. a department's original
        submission, kept byte for byte as evidence of what was parsed."""
        ...

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        ...

    @abstractmethod
    def lock(self, path: str) -> AbstractContextManager:
        """`with storage.lock(path):` -- serialize read-modify-write access
        to `path` across every process that shares this storage: threads
        and processes on one machine for local storage, and every machine
        writing to the same bucket for S3/Wasabi."""
        ...
