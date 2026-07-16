import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.db import registry
from app.db.sources import (
    UPLOADS_DIR,
    DuckDBSource,
    SQLiteSource,
    sanitize_filename,
)
from app.models.schemas import SourceInfo, SourceUploadResponse
from app.api import query as query_module

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

DUCKDB_EXTS = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}
SQLITE_EXTS = {".db", ".sqlite", ".sqlite3"}


def _source_info(source_id: str, source) -> SourceInfo:
    try:
        tables = source.list_tables()
    except Exception:
        tables = []
    return SourceInfo(source_id=source_id, name=source.name, dialect=source.dialect, tables=tables)


@router.get("/sources", response_model=list[SourceInfo])
def list_sources():
    registry.ensure_clickhouse()  # surface the env ClickHouse source if reachable
    return [_source_info(sid, src) for sid, src in registry.list_sources()]


@router.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_source(file: UploadFile = File(...), source_id: str | None = Form(None)):
    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext in DUCKDB_EXTS:
        kind = "duckdb"
    elif ext in SQLITE_EXTS:
        kind = "sqlite"
    else:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. "
                   f"Accepted: {', '.join(sorted(DUCKDB_EXTS | SQLITE_EXTS))}.",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB).")

    # add to an existing DuckDB source (enables cross-file joins) or create a new one
    if source_id is not None:
        source = registry.get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'.")
        if not isinstance(source, DuckDBSource):
            raise HTTPException(status_code=400, detail="Files can only be added to a DuckDB source.")
        if kind != "duckdb":
            raise HTTPException(status_code=400, detail="SQLite files always create their own source.")
        sid = source_id
    else:
        sid = registry.new_source_id()
        source = None

    source_dir = UPLOADS_DIR / sid
    source_dir.mkdir(parents=True, exist_ok=True)
    file_path = source_dir / sanitize_filename(original_name)
    file_path.write_bytes(data)

    try:
        if source is not None:
            source.add_file(file_path, original_name)
        elif kind == "duckdb":
            source = DuckDBSource(name=original_name, source_dir=source_dir)
            source.add_file(file_path, original_name)
        else:
            source = SQLiteSource(name=original_name, db_path=file_path)
            source.test_connection()  # fail fast on a corrupt/non-sqlite file
    except Exception as e:
        if registry.get(sid) is None:
            shutil.rmtree(source_dir, ignore_errors=True)  # clean up failed new source
        raise HTTPException(status_code=400, detail=f"Could not load '{original_name}': {e}")

    registry.register(sid, source)
    query_module._schema_cache.pop(sid, None)  # schema changed — drop any cached copy
    info = _source_info(sid, source)
    return SourceUploadResponse(**info.model_dump(), schema_preview=source.get_schema()[:1500])


@router.delete("/sources/{source_id}")
def delete_source(source_id: str):
    source = registry.unregister(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'.")
    if hasattr(source, "close"):
        source.close()
    shutil.rmtree(UPLOADS_DIR / source_id, ignore_errors=True)
    return {"status": "deleted", "source_id": source_id}
