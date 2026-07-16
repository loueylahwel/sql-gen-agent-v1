import re
import sqlparse

BLOCKED = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|SYSTEM|KILL)\b",
    re.IGNORECASE,
)

def validate(sql: str) -> None:
    if not sql or not sql.strip():
        raise ValueError("Empty SQL generated.")
    if BLOCKED.search(sql):
        raise ValueError("Generated SQL contains a forbidden keyword.")
    # reject multiple statements (allow one trailing empty statement after ';')
    statements = [s for s in sql.split(";") if s.strip()]
    if len(statements) > 1:
        raise ValueError("Generated SQL contains multiple statements.")
    parsed = sqlparse.parse(sql)
    if not parsed:
        raise ValueError("Could not parse the generated SQL.")
