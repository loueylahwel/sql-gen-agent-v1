from app.core.config import settings

try:
    import clickhouse_connect
except ImportError:  # app must boot without it; only the ClickHouse source needs it
    clickhouse_connect = None

def get_client():
    if clickhouse_connect is None:
        raise RuntimeError(
            "clickhouse-connect is not installed. "
            "Install it with 'pip install clickhouse-connect' to use the ClickHouse source."
        )
    return clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_HOST,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        secure=settings.CLICKHOUSE_SECURE,
    )

def run_query(sql: str) -> tuple[list[str], list[tuple]]:
    client = get_client()
    result = client.query(sql)
    columns = list(result.column_names)
    rows = [list(row) for row in result.result_set]
    return columns, rows

def test_connection() -> bool:
    try:
        get_client().query("SELECT 1")
        return True
    except Exception:
        return False
