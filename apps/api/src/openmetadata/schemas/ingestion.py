from pydantic import BaseModel, ConfigDict
from typing import Any


class PipelineTriggerRequest(BaseModel):
    pipeline_id: str


class PipelineTriggerResponse(BaseModel):
    status: str
    pipeline_id: str
    detail: dict[str, Any] | None = None


class PostgresIngestionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    service_name: str = "postgres_appdb"
    host: str = "localhost"
    port: int = 5432
    database: str = "appdb"
    username: str = "postgres"
    password: str = ""
    include_tables: list[str] | None = None
    exclude_tables: list[str] | None = None


class CsvIngestionConfig(BaseModel):
    file_path: str
    table_name: str
    delimiter: str = ","
    has_header: bool = True
    columns: list[dict[str, str]] | None = None
    encoding: str = "utf-8-sig"


class CsvUploadResponse(BaseModel):
    file_path: str
    filename: str
    size: int


class IngestionPipelineDef(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    pipelineType: str = "metadata"
    sourceConfig: dict[str, Any] | None = None
    sinkConfig: dict[str, Any] | None = None
    serviceId: str | None = None
