from app.db.connection import get_client
from app.core.config import settings

def get_schema() -> str:
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
        schema_parts.append(create_stmt)

    return "\n\n".join(schema_parts)

def get_tables() -> list[str]:
    client = get_client()
    db = settings.CLICKHOUSE_DATABASE
    rows = client.query(
        "SELECT name FROM system.tables WHERE database = {db:String} AND engine NOT LIKE '%View%'",
        parameters={"db": db},
    ).result_set
    return [r[0] for r in rows]