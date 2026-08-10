from abc import ABC, abstractmethod
from typing import Any

from src.openmetadata.client import OpenMetadataClient


class BaseConnector(ABC):
    """Override to supply source-specific metadata entities to OM."""

    @abstractmethod
    async def extract_entities(self, client: OpenMetadataClient) -> list[dict]:
        ...

    @abstractmethod
    async def ingest(self, client: OpenMetadataClient) -> dict[str, Any]:
        ...


class BaseIngestionService(ABC):
    connector: BaseConnector

    @abstractmethod
    async def run(self, client: OpenMetadataClient) -> dict[str, Any]:
        ...
