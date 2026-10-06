from typing import Literal

from pydantic import BaseModel, Field


Visibility = Literal["public", "department", "restricted", "confidential"]


class DatasetColumn(BaseModel):
    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    description: str | None = None


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1)
    display_name: str | None = None
    description: str | None = None
    database_service: str = Field(min_length=1)
    database: str = Field(min_length=1)
    database_schema: str = Field(min_length=1, default="public")
    columns: list[DatasetColumn] = Field(min_length=1)
    visibility: Visibility = "department"
    department: str | None = Field(default=None, description="Owning department; defaults to the service name")
    # Dataset information tags (mirrored from the OM Custom Properties panel).
    api_available: bool | None = Field(default=None, description="Whether this dataset is exposed via an API (Y/N)")
    dataset_owner: str | None = Field(default=None, max_length=255, description="Who owns/is accountable for this dataset (free text)")
    frequency: str | None = Field(default=None, max_length=100, description="How often this dataset is refreshed/submitted")
    timeline: str | None = Field(default=None, max_length=255, description="The period/date range this dataset covers")


class DatasetResponse(BaseModel):
    success: bool
    message: str
    data: dict


class AccessRequestCreate(BaseModel):
    fqn: str = Field(min_length=1, description="Table or dataset FQN access is requested for")
    note: str | None = Field(default=None, max_length=1000)


class AccessRequestOut(BaseModel):
    id: int
    fqn: str
    status: str
