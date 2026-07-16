from pydantic import BaseModel
from typing import Any

class QueryRequest(BaseModel):
    question: str
    source_id: str | None = None  # default: the only registered source

class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    answer: str
    source_id: str = ""
    source_name: str = ""

class SchemaResponse(BaseModel):
    database: str
    tables: list[str]
    ddl: str

class SourceInfo(BaseModel):
    source_id: str
    name: str
    dialect: str
    tables: list[str]

class SourceUploadResponse(SourceInfo):
    schema_preview: str
