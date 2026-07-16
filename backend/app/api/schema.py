from fastapi import APIRouter, HTTPException
from app.db import registry
from app.db.connection import test_connection
from app.models.schemas import SchemaResponse
from app.api import query as query_module

router = APIRouter()

@router.get("/schema", response_model=SchemaResponse)
def schema(source_id: str | None = None):
    sid, source = registry.resolve_source(source_id)
    try:
        return SchemaResponse(
            database=source.name,
            tables=source.list_tables(),
            ddl=source.get_schema(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schema/refresh")
def refresh_schema(source_id: str | None = None):
    if source_id:
        query_module._schema_cache.pop(source_id, None)
    else:
        query_module._schema_cache.clear()
    registry.reset_clickhouse()  # retry lazy registration if ClickHouse was down
    return {"status": "schema cache cleared"}

@router.get("/health/db")
def db_health():
    ok = test_connection()
    return {"clickhouse": "ok" if ok else "unreachable"}
