from typing import Literal

from pydantic import BaseModel, Field


Visibility = Literal["public", "department", "restricted", "confidential"]


class DatasetColumn(BaseModel):
    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    description: str | None = None


class DatasetInfoFields(BaseModel):
    """Dataset-level defaults every member table inherits unless it overrides them."""

    owner: str | None = Field(default=None, max_length=255, description="Who owns/is accountable for the dataset")
    steward: str | None = Field(default=None, max_length=255, description="Data steward for the dataset")
    frequency: str | None = Field(default=None, max_length=100, description="Default refresh frequency of its tables")
    timeline: str | None = Field(default=None, max_length=255, description="The period/date range the dataset covers")


class DatasetInfoUpdate(DatasetInfoFields):
    fqn: str = Field(min_length=1, description="Dataset FQN (service.database)")


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
    # Table-level information. Owner/frequency/timeline here override the
    # dataset defaults for this table only; leave them empty to inherit.
    api_available: bool | None = Field(default=None, description="Whether this table is exposed via an API (Y/N)")
    dataset_owner: str | None = Field(default=None, max_length=255, description="Per-table owner override (free text); empty inherits the dataset owner")
    frequency: str | None = Field(default=None, max_length=100, description="Per-table refresh frequency override")
    timeline: str | None = Field(default=None, max_length=255, description="Per-table covered period override")
    # Dataset-level defaults for the parent dataset (OM database). Only the
    # fields provided are written, so adding a table never clears them.
    dataset_info: DatasetInfoFields | None = None


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
