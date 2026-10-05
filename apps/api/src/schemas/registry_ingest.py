from datetime import datetime

from pydantic import BaseModel, Field


class IngestedColumn(BaseModel):
    position: int
    name: str
    data_type: str
    length: int | None = None
    scale: int | None = None
    nullable: bool
    default_value: str | None = None
    business_description: str | None = None
    tag: str | None = None
    classification: str | None = None
    glossary_term: str | None = None
    active: bool
    validation_warning: str | None = None


class IngestedTable(BaseModel):
    table_id: str
    department: str
    dataset: str
    schema_name: str
    table_name: str
    column_count: int
    source_timestamp: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IngestedTableDetail(IngestedTable):
    columns: list[IngestedColumn] = Field(default_factory=list)


class IngestResponse(BaseModel):
    table_id: str
    department: str
    dataset: str
    schema_name: str
    table_name: str
    column_count: int
    source_timestamp: str | None = None
    uploaded_by: str | None = None
