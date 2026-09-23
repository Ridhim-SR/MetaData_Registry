from pydantic import BaseModel, Field


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


class DatasetResponse(BaseModel):
    success: bool
    message: str
    data: dict
