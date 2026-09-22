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
    def exists(self, path: str) -> bool:
        ...

    @abstractmethod
    def list(self, prefix: str) -> list[str]:
        ...
