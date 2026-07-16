import re
import threading
import time
from groq import (
    Groq,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from app.core.config import settings


def _list_keys() -> list[str]:
    keys = []
    for k in settings.GROQ_API_KEYS.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    single = settings.GROQ_API_KEY.strip()
    if single and single not in keys:
        keys.append(single)
    if not keys:
        raise RuntimeError(
            "No Groq API key configured. Set GROQ_API_KEYS (comma-separated) or "
            "GROQ_API_KEY in backend/.env (get keys at https://console.groq.com)."
        )
    return keys


class _KeyPool:
    def __init__(self, keys):
        self._keys = list(keys)
        self._dead = set()
        self._i = 0
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            alive = [k for k in self._keys if k not in self._dead]
            if not alive:
                raise RuntimeError(
                    "All configured Groq API keys were rejected (401). "
                    "Check GROQ_API_KEYS in backend/.env."
                )
            key = alive[self._i % len(alive)]
            self._i += 1
            return key

    def mark_dead(self, key):
        with self._lock:
            self._dead.add(key)


_clients: dict[str, Groq] = {}
_pool: _KeyPool | None = None


def _get_pool() -> _KeyPool:
    global _pool
    if _pool is None:
        _pool = _KeyPool(_list_keys())
    return _pool


def _get_client(api_key: str) -> Groq:
    client = _clients.get(api_key)
    if client is None:
        client = Groq(api_key=api_key)
        _clients[api_key] = client
    return client


def _retry_delay(exc, attempt):
    match = re.search(r"try again in ([\d.]+)s", str(exc), re.IGNORECASE)
    if match:
        return float(match.group(1)) + 0.5
    return min(2.0 * (2 ** attempt), 60.0)


def _chat(prompt: str, max_attempts: int = 8) -> str:
    """Send a prompt to Groq, rotating API keys on rate limits or transient errors.

    Authentication failures mark a key as dead immediately. The function retries
    across the remaining keys with backoff so one exhausted org key does not
    kill the whole request.
    """
    last_exc = None
    for attempt in range(max_attempts):
        key = _get_pool().acquire()
        try:
            client = _get_client(key)
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return response.choices[0].message.content.strip()
        except AuthenticationError as exc:
            _get_pool().mark_dead(key)
            last_exc = exc
        except (RateLimitError, APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            time.sleep(_retry_delay(exc, attempt))
    raise last_exc


DIALECT_HINTS = {
    "DuckDB": (
        "Use DuckDB / standard SQL syntax. The tables listed in the schema already exist "
        "as views — query them directly, do NOT use read_csv_auto or file paths."
    ),
    "SQLite": (
        "Use SQLite syntax: LIKE instead of ILIKE, date()/strftime() for date handling, "
        "use standard SQLite functions."
    ),
}


def _dialect_hint(dialect: str) -> str:
    return DIALECT_HINTS.get(dialect, f"Use {dialect} syntax.")


def build_sql_prompt(schema: str, question: str, dialect: str = "DuckDB") -> str:
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


def build_fix_prompt(schema: str, question: str, bad_sql: str, error: str, dialect: str = "DuckDB") -> str:
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


def generate_sql(schema: str, question: str, dialect: str = "DuckDB") -> str:
    return _extract_sql(_chat(build_sql_prompt(schema, question, dialect)))


def fix_sql(schema: str, question: str, bad_sql: str, error: str, dialect: str = "DuckDB") -> str:
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
