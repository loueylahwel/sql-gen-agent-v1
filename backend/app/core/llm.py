import re
import ollama
from app.core.config import settings


def _get_client():
    return ollama.Client(host=settings.OLLAMA_HOST)


def build_sql_prompt(schema: str, question: str) -> str:
    return f"""You are an expert ClickHouse SQL assistant.
Given the following ClickHouse database schema, write a SQL query that answers the user's question.

Rules:
- Output ONLY the raw SQL query, no explanation, no markdown, no backticks
- Use only SELECT statements. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE
- Use ClickHouse syntax (toDate(), toDateTime(), uniq(), countIf(), etc.)
- Add LIMIT {settings.ROW_LIMIT} unless the query returns a single aggregated row

Schema:
{schema}

Question: {question}

SQL:"""


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


def generate_sql(schema: str, question: str) -> str:
    prompt = build_sql_prompt(schema, question)
    client = _get_client()
    response = client.chat(
        model=settings.OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"].strip()
    return _extract_sql(raw)


def generate_answer(question: str, columns: list, rows: list) -> str:
    prompt = build_answer_prompt(question, columns, rows)
    client = _get_client()
    response = client.chat(
        model=settings.OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def _extract_sql(raw: str) -> str:
    raw = re.sub(r"```(?:sql)?", "", raw, flags=re.IGNORECASE)
    return raw.strip("` \n").strip()