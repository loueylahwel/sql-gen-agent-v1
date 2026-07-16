from fastapi import APIRouter, HTTPException
from app.core.llm import generate_sql, fix_sql, generate_answer
from app.core.validator import validate
from app.db.connection import run_query
from app.db.introspect import get_schema
from app.models.schemas import QueryRequest, QueryResponse

router = APIRouter()

MAX_ATTEMPTS = 3

_schema_cache: str | None = None

def _get_cached_schema() -> str:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = get_schema()
    return _schema_cache

@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        schema = _get_cached_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    sql = None
    last_error: str | None = None
    columns, rows = [], []

    for attempt in range(MAX_ATTEMPTS):
        try:
            if sql is None:
                sql = generate_sql(schema, request.question)
            else:
                sql = fix_sql(schema, request.question, sql, last_error)
            validate(sql)
            columns, rows = run_query(sql)
            last_error = None
            break
        except ValueError as e:  # validation failure
            last_error = str(e)
        except Exception as e:  # execution failure
            last_error = str(e)

    if last_error is not None:
        raise HTTPException(status_code=422, detail=last_error)

    try:
        answer = generate_answer(request.question, columns, rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return QueryResponse(
        question=request.question,
        sql=sql,
        columns=columns,
        rows=[list(r) for r in rows],
        row_count=len(rows),
        answer=answer,
    )
