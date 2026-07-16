"""In-memory registry of data sources, keyed by source_id.

The env-configured ClickHouse source is registered lazily under the well-known
id "clickhouse" on first successful connection — the app must boot even when
ClickHouse is down or unconfigured.
"""
import threading
import uuid

from fastapi import HTTPException

from app.core.config import settings
from app.db.sources import ClickHouseSource, DataSource

CLICKHOUSE_SOURCE_ID = "clickhouse"

_lock = threading.Lock()
_sources: dict[str, DataSource] = {}

# "unattempted" | "ok" | "failed" — a failed ClickHouse registration is not
# retried on every request (connection timeouts are slow); reset via refresh.
_clickhouse_state = "unattempted"


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


def ensure_clickhouse() -> DataSource | None:
    """Register the env ClickHouse source on first successful connection."""
    global _clickhouse_state
    existing = get(CLICKHOUSE_SOURCE_ID)
    if existing is not None:
        return existing
    if _clickhouse_state == "failed" or not settings.CLICKHOUSE_HOST:
        return None
    candidate = ClickHouseSource()
    if not candidate.test_connection():
        _clickhouse_state = "failed"
        return None
    register(CLICKHOUSE_SOURCE_ID, candidate)
    _clickhouse_state = "ok"
    return candidate


def reset_clickhouse() -> None:
    """Allow the lazy ClickHouse registration to be attempted again."""
    global _clickhouse_state
    with _lock:
        _sources.pop(CLICKHOUSE_SOURCE_ID, None)
    _clickhouse_state = "unattempted"


def resolve_source(source_id: str | None) -> tuple[str, DataSource]:
    """Resolve the source to query: explicit id → ClickHouse → the only source."""
    if source_id:
        source = get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'.")
        return source_id, source

    clickhouse = ensure_clickhouse()
    if clickhouse is not None:
        return CLICKHOUSE_SOURCE_ID, clickhouse

    sources = list_sources()
    if len(sources) == 1:
        return sources[0]
    if not sources:
        raise HTTPException(
            status_code=400,
            detail="No data source configured. Set CLICKHOUSE_* in backend/.env "
                   "or upload a file via POST /api/sources/upload.",
        )
    raise HTTPException(
        status_code=400,
        detail="Multiple data sources registered; specify source_id.",
    )
