from abc import ABC, abstractmethod


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
    def lock_path(self, path: str) -> str:
        """A filesystem path usable with filelock.FileLock to serialize
        concurrent read-modify-write access to the file at `path`."""
        ...
