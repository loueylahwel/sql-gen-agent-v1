from pydantic import BaseModel
from typing import Any

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    answer: str

class SchemaResponse(BaseModel):
    database: str
    tables: list[str]
    ddl: str