from fastapi import APIRouter, HTTPException
from app.db.introspect import get_schema, get_tables
from app.db.connection import test_connection
from app.models.schemas import SchemaResponse
from app.core.config import settings
from app.api import query as query_module

router = APIRouter()

@router.get("/schema", response_model=SchemaResponse)
def schema():
    try:
        ddl = get_schema()
        tables = get_tables()
        return SchemaResponse(
            database=settings.CLICKHOUSE_DATABASE,
            tables=tables,
            ddl=ddl,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schema/refresh")
def refresh_schema():
    query_module._schema_cache = None
    return {"status": "schema cache cleared"}

@router.get("/health/db")
def db_health():
    ok = test_connection()
    return {"clickhouse": "ok" if ok else "unreachable"}