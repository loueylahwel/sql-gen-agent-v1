from fastapi import APIRouter, HTTPException
from app.core.llm import generate_sql, fix_sql, generate_answer
from app.core.validator import validate
from app.db import registry
from app.models.schemas import QueryRequest, QueryResponse

router = APIRouter()

MAX_ATTEMPTS = 3

_schema_cache: dict[str, str] = {}  # per source_id

def _get_cached_schema(source_id: str, source) -> str:
    if source_id not in _schema_cache:
        _schema_cache[source_id] = source.get_schema()
    return _schema_cache[source_id]

@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    source_id, source = registry.resolve_source(request.source_id)
    try:
        schema = _get_cached_schema(source_id, source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    sql = None
    last_error: str | None = None
    columns, rows = [], []

    for attempt in range(MAX_ATTEMPTS):
        try:
            if sql is None:
                sql = generate_sql(schema, request.question, source.dialect)
            else:
                sql = fix_sql(schema, request.question, sql, last_error, source.dialect)
            validate(sql)
            columns, rows = source.run_query(sql)
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
        source_id=source_id,
        source_name=source.name,
    )
