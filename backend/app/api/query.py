from fastapi import APIRouter, HTTPException
from app.core.llm import generate_sql, generate_answer
from app.core.validator import validate
from app.db.connection import run_query
from app.db.introspect import get_schema
from app.models.schemas import QueryRequest, QueryResponse

router = APIRouter()

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
        sql = generate_sql(schema, request.question)
        validate(sql)
        columns, rows = run_query(sql)
        answer = generate_answer(request.question, columns, rows)
        return QueryResponse(
            question=request.question,
            sql=sql,
            columns=columns,
            rows=[list(r) for r in rows],
            row_count=len(rows),
            answer=answer,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))