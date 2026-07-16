"""In-memory registry of data sources, keyed by source_id.

Uploaded DuckDB and SQLite sources are registered here after a successful upload.
"""
import threading
import uuid

from fastapi import HTTPException

from app.db.sources import DataSource

_lock = threading.Lock()
_sources: dict[str, DataSource] = {}


def new_source_id() -> str:
    return uuid.uuid4().hex[:8]


def register(source_id: str, source: DataSource) -> None:
    with _lock:
        _sources[source_id] = source


def get(source_id: str) -> DataSource | None:
    with _lock:
        return _sources.get(source_id)


def unregister(source_id: str) -> DataSource | None:
    with _lock:
        return _sources.pop(source_id, None)


def list_sources() -> list[tuple[str, DataSource]]:
    with _lock:
        return list(_sources.items())


def resolve_source(source_id: str | None) -> tuple[str, DataSource]:
    """Resolve the source to query: explicit id → the only source."""
    if source_id:
        source = get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'.")
        return source_id, source

    sources = list_sources()
    if len(sources) == 1:
        return sources[0]
    if not sources:
        raise HTTPException(
            status_code=400,
            detail="No data source configured. Upload a file via POST /api/sources/upload.",
        )
    raise HTTPException(
        status_code=400,
        detail="Multiple data sources registered; specify source_id.",
    )
