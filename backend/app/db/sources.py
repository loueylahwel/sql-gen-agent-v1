"""Data source abstraction: ClickHouse (env), DuckDB (uploaded files), SQLite (uploaded .db).

Every source exposes the same interface so the query pipeline stays source-agnostic:
schema discovery (columns + sample rows), table listing, query execution, health check.
"""
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.db.connection import get_client

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"

SAMPLE_ROWS = 2               # sample rows per table shown to the LLM
MAX_SAMPLE_COLUMNS = 20       # only the first N columns are sampled
MAX_COLUMNS_FOR_SAMPLE = 50   # skip sampling entirely for very wide tables


@runtime_checkable
class DataSource(Protocol):
    name: str
    dialect: str  # "ClickHouse", "DuckDB", "SQLite"

    def get_schema(self) -> str: ...
    def list_tables(self) -> list[str]: ...
    def run_query(self, sql: str) -> tuple[list[str], list[tuple]]: ...
    def test_connection(self) -> bool: ...


# ── shared helpers ──────────────────────────────────────────────────────────

def sanitize_identifier(name: str, taken: set[str]) -> str:
    """Turn a file/table name into a safe SQL identifier, deduped against `taken`."""
    base = re.sub(r"\W+", "_", name).strip("_").lower() or "data"
    if base[0].isdigit():
        base = f"t_{base}"
    candidate, i = base, 2
    while candidate in taken:
        candidate = f"{base}_{i}"
        i += 1
    taken.add(candidate)
    return candidate


def sanitize_filename(name: str) -> str:
    """Keep the original filename but strip anything unsafe for disk storage."""
    cleaned = re.sub(r"[^\w.\-]+", "_", name).strip("._")
    return cleaned or "upload"


def _columns_to_sample(columns: list) -> list | None:
    """Which columns to include in sample rows (None = skip sampling for this table)."""
    if len(columns) > MAX_COLUMNS_FOR_SAMPLE:
        return None
    return [name for name, _ in columns[:MAX_SAMPLE_COLUMNS]]


def _format_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        text = value if len(value) <= 80 else value[:77] + "..."
        return "'" + text.replace("'", "''") + "'"
    return str(value)


def _format_table_schema(table: str, columns: list, sample_rows: list) -> str:
    """Uniform prompt format: 'Table: x / Columns: ... / Sample rows: ...'."""
    lines = [f"Table: {table}"]
    lines.append("Columns: " + ", ".join(f"{name} {ctype}" for name, ctype in columns))
    if sample_rows:
        lines.append("Sample rows:")
        for row in sample_rows:
            lines.append("  (" + ", ".join(_format_value(v) for v in row) + ")")
    return "\n".join(lines)


# ── ClickHouse (configured via backend/.env) ─────────────────────────────────

class ClickHouseSource:
    dialect = "ClickHouse"

    def __init__(self):
        self.name = f"ClickHouse ({settings.CLICKHOUSE_DATABASE})"

    def test_connection(self) -> bool:
        try:
            get_client().query("SELECT 1")
            return True
        except Exception:
            return False

    def run_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        client = get_client()
        result = client.query(sql)
        return list(result.column_names), [list(row) for row in result.result_set]

    def list_tables(self) -> list[str]:
        client = get_client()
        rows = client.query(
            "SELECT name FROM system.tables WHERE database = {db:String} AND engine NOT LIKE '%View%'",
            parameters={"db": settings.CLICKHOUSE_DATABASE},
        ).result_set
        return [r[0] for r in rows]

    def get_schema(self) -> str:
        client = get_client()
        db = settings.CLICKHOUSE_DATABASE

        tables = client.query(
            "SELECT name FROM system.tables WHERE database = {db:String} AND engine NOT LIKE '%View%'",
            parameters={"db": db},
        ).result_set

        if not tables:
            return "-- No tables found in database."

        schema_parts = []
        for (table_name,) in tables:
            columns = client.query(
                "SELECT name, type, comment FROM system.columns WHERE database = {db:String} AND table = {table:String} ORDER BY position",
                parameters={"db": db, "table": table_name},
            ).result_set

            engine_rows = client.query(
                "SELECT engine, partition_key, sorting_key FROM system.tables WHERE database = {db:String} AND name = {table:String}",
                parameters={"db": db, "table": table_name},
            ).result_set

            col_defs = []
            for col_name, col_type, comment in columns:
                line = f"    `{col_name}` {col_type}"
                if comment:
                    line += f"  -- {comment}"
                col_defs.append(line)

            create_stmt = f"CREATE TABLE {db}.{table_name} (\n" + ",\n".join(col_defs) + "\n)"

            if engine_rows:
                engine, partition_key, sorting_key = engine_rows[0]
                create_stmt += f"\nENGINE = {engine}"
                if partition_key:
                    create_stmt += f"\nPARTITION BY {partition_key}"
                if sorting_key:
                    create_stmt += f"\nORDER BY {sorting_key}"

            create_stmt += ";"
            create_stmt += self._sample_rows_clause(client, db, table_name, columns)
            schema_parts.append(create_stmt)

        return "\n\n".join(schema_parts)

    def _sample_rows_clause(self, client, db: str, table: str, columns: list) -> str:
        sample_cols = _columns_to_sample([(c[0], c[1]) for c in columns])
        if not sample_cols:
            return ""
        col_list = ", ".join(f"`{c}`" for c in sample_cols)
        try:
            rows = client.query(f"SELECT {col_list} FROM `{db}`.`{table}` LIMIT {SAMPLE_ROWS}").result_set
        except Exception:
            return ""  # sampling is best-effort; never break schema discovery
        if not rows:
            return ""
        lines = ["-- Sample rows:"]
        for row in rows:
            lines.append("--   (" + ", ".join(_format_value(v) for v in row) + ")")
        return "\n" + "\n".join(lines)


# ── DuckDB (uploaded CSV / Excel / JSON / Parquet files) ─────────────────────

class DuckDBSource:
    dialect = "DuckDB"

    def __init__(self, name: str, source_dir: Path):
        import duckdb  # imported here so the app still boots if duckdb is missing

        self.name = name
        self.source_dir = source_dir
        self._con = duckdb.connect(database=":memory:")
        self._lock = threading.Lock()  # duckdb connections are not thread-safe
        self._views: list[str] = []
        self._taken: set[str] = set()

    def add_file(self, file_path: Path, original_name: str) -> str:
        """Register an uploaded file as a view; returns the view name."""
        ext = file_path.suffix.lower()
        view = sanitize_identifier(Path(original_name).stem, self._taken)
        with self._lock:
            if ext in (".xlsx", ".xls"):
                # pandas -> register is the most reliable offline path for Excel
                import pandas as pd

                df = pd.read_excel(file_path)
                self._con.register(view, df)
            elif ext == ".parquet":
                self._execute(f'CREATE OR REPLACE VIEW "{view}" AS SELECT * FROM read_parquet(\'{_sql_path(file_path)}\')')
            elif ext in (".json", ".jsonl"):
                self._execute(f'CREATE OR REPLACE VIEW "{view}" AS SELECT * FROM read_json_auto(\'{_sql_path(file_path)}\')')
            else:  # .csv / .tsv — read_csv_auto sniffs delimiter and header
                self._execute(f'CREATE OR REPLACE VIEW "{view}" AS SELECT * FROM read_csv_auto(\'{_sql_path(file_path)}\')')
            self._views.append(view)
        return view

    def _execute(self, sql: str):
        self._con.execute(sql)

    def list_tables(self) -> list[str]:
        return list(self._views)

    def test_connection(self) -> bool:
        try:
            with self._lock:
                self._con.execute("SELECT 1")
            return True
        except Exception:
            return False

    def run_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        with self._lock:
            result = self._con.execute(sql)
            columns = [d[0] for d in result.description]
            return columns, result.fetchall()

    def get_schema(self) -> str:
        if not self._views:
            return "-- No tables found in database."
        schema_parts = []
        for view in self._views:
            with self._lock:
                columns = [
                    (row[0], row[1])
                    for row in self._con.execute(f'DESCRIBE "{view}"').fetchall()
                ]
                sample_rows = self._sample_rows(view, columns)
            schema_parts.append(_format_table_schema(view, columns, sample_rows))
        return "\n\n".join(schema_parts)

    def _sample_rows(self, view: str, columns: list) -> list:
        sample_cols = _columns_to_sample(columns)
        if not sample_cols:
            return []
        col_list = ", ".join(f'"{c}"' for c in sample_cols)
        try:
            return self._con.execute(f'SELECT {col_list} FROM "{view}" LIMIT {SAMPLE_ROWS}').fetchall()
        except Exception:
            return []  # sampling is best-effort

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass


# ── SQLite (uploaded .db / .sqlite files) ────────────────────────────────────

class SQLiteSource:
    dialect = "SQLite"

    def __init__(self, name: str, db_path: Path):
        self.name = name
        self.db_path = db_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    @contextmanager
    def _session(self):
        """Locked connection that is always closed (file handles matter on Windows)."""
        with self._lock:
            con = self._connect()
            try:
                yield con
            finally:
                con.close()

    def test_connection(self) -> bool:
        try:
            with self._session() as con:
                con.execute("SELECT 1")
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        with self._session() as con:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]

    def run_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        with self._session() as con:
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description or []]
            return columns, cursor.fetchall()

    def get_schema(self) -> str:
        tables = self.list_tables()
        if not tables:
            return "-- No tables found in database."
        schema_parts = []
        with self._session() as con:
            for table in tables:
                columns = [
                    (row[1], row[2] or "UNKNOWN")
                    for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()
                ]
                sample_rows = self._sample_rows(con, table, columns)
                schema_parts.append(_format_table_schema(table, columns, sample_rows))
        return "\n\n".join(schema_parts)

    def _sample_rows(self, con: sqlite3.Connection, table: str, columns: list) -> list:
        sample_cols = _columns_to_sample(columns)
        if not sample_cols:
            return []
        col_list = ", ".join(f'"{c}"' for c in sample_cols)
        try:
            return con.execute(f'SELECT {col_list} FROM "{table}" LIMIT {SAMPLE_ROWS}').fetchall()
        except Exception:
            return []  # sampling is best-effort


def _sql_path(path: Path) -> str:
    """Render a filesystem path safely inside a single-quoted SQL string."""
    return path.as_posix().replace("'", "''")
