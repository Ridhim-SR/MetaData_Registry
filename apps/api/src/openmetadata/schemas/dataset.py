from typing import Literal

from pydantic import BaseModel, Field


Visibility = Literal["public", "department", "restricted"]


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
