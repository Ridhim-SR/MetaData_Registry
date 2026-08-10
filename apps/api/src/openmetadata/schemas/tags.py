from typing import Literal

from pydantic import BaseModel


class ClassificationCreate(BaseModel):
    name: str
    displayName: str | None = None
    description: str | None = None


class TagCreate(BaseModel):
    classification: str
    name: str
    displayName: str | None = None
    description: str | None = None


class GlossaryCreate(BaseModel):
    name: str
    displayName: str | None = None
    description: str | None = None


class GlossaryTermCreate(BaseModel):
    glossary: str
    name: str
    displayName: str | None = None
    description: str | None = None


class TableTagLabel(BaseModel):
    tagFQN: str
    source: Literal["Tag", "Glossary"] = "Tag"
    fieldPath: str | None = None


class TableTagUpdate(BaseModel):
    labels: list[TableTagLabel]
