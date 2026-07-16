"""Thin compatibility wrapper — the implementation moved to app.db.sources.ClickHouseSource."""
from app.db.sources import ClickHouseSource


def get_schema() -> str:
    return ClickHouseSource().get_schema()


def get_tables() -> list[str]:
    return ClickHouseSource().list_tables()
