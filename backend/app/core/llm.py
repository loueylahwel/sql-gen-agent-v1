import re
from groq import Groq
from app.core.config import settings

_client: Groq | None = None


def _get_client() -> Groq:
    """Create the Groq client lazily so the app can boot without a key."""
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to backend/.env "
                "(get a key at https://console.groq.com)."
            )
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


DIALECT_HINTS = {
    "ClickHouse": "Use ClickHouse syntax (toDate(), toDateTime(), uniq(), countIf(), etc.)",
    "DuckDB": (
        "Use DuckDB / standard SQL syntax. The tables listed in the schema already exist "
        "as views — query them directly, do NOT use read_csv_auto or file paths."
    ),
    "SQLite": (
        "Use SQLite syntax: LIKE instead of ILIKE, date()/strftime() for date handling, "
        "no ClickHouse-specific functions."
    ),
}


def _dialect_hint(dialect: str) -> str:
    return DIALECT_HINTS.get(dialect, f"Use {dialect} syntax.")


def build_sql_prompt(schema: str, question: str, dialect: str = "ClickHouse") -> str:
    return f"""You are an expert {dialect} SQL assistant.
Given the following {dialect} database schema, write a SQL query that answers the user's question.

Rules:
- Output ONLY the raw SQL query, no explanation, no markdown, no backticks
- Use only SELECT statements. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE
- {_dialect_hint(dialect)}
- Add LIMIT {settings.ROW_LIMIT} unless the query returns a single aggregated row

Schema:
{schema}

Question: {question}

SQL:"""


def build_fix_prompt(schema: str, question: str, bad_sql: str, error: str, dialect: str = "ClickHouse") -> str:
    return f"""You are an expert {dialect} SQL assistant.
A SQL query generated for the user's question failed. Fix it.

Rules:
- Output ONLY the corrected raw SQL query, no explanation, no markdown, no backticks
- Use only SELECT statements. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE
- {_dialect_hint(dialect)}
- Add LIMIT {settings.ROW_LIMIT} unless the query returns a single aggregated row

Schema:
{schema}

Question: {question}

Failed SQL:
{bad_sql}

Error:
{error}

Corrected SQL:"""


def build_answer_prompt(question: str, columns: list, rows: list) -> str:
    # Format results as a simple table string
    if not rows:
        results_str = "No results found."
    else:
        header = " | ".join(str(c) for c in columns)
        lines = [header, "-" * len(header)]
        for row in rows[:20]:  # cap at 20 rows for the prompt
            lines.append(" | ".join(str(v) for v in row))
        if len(rows) > 20:
            lines.append(f"... and {len(rows) - 20} more rows")
        results_str = "\n".join(lines)

    return f"""You are a helpful data analyst assistant.
A user asked: "{question}"

The query returned these results:
{results_str}

Answer the user's question in plain English based on these results.
Be concise and direct. Do not mention SQL or technical details.
If the results are empty, say so clearly.
Answer:"""


def _chat(prompt: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def generate_sql(schema: str, question: str, dialect: str = "ClickHouse") -> str:
    return _extract_sql(_chat(build_sql_prompt(schema, question, dialect)))


def fix_sql(schema: str, question: str, bad_sql: str, error: str, dialect: str = "ClickHouse") -> str:
    return _extract_sql(_chat(build_fix_prompt(schema, question, bad_sql, error, dialect)))


def generate_answer(question: str, columns: list, rows: list) -> str:
    return _chat(build_answer_prompt(question, columns, rows))


def _extract_sql(raw: str) -> str:
    # strip markdown fences
    raw = re.sub(r"```(?:sql)?", "", raw, flags=re.IGNORECASE)
    raw = raw.strip("` \n")
    # if the model added prose around the SQL, start at the first SELECT/WITH
    match = re.search(r"\b(SELECT|WITH)\b", raw, re.IGNORECASE)
    if match:
        raw = raw[match.start():]
    return raw.strip()
