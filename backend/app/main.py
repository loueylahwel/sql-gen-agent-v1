from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import query, schema, sources
from app.db.sources import UPLOADS_DIR

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Text-to-SQL Agent v2",
    description="Natural language to SQL over ClickHouse, uploaded files (DuckDB) and SQLite, using Groq",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router,   prefix="/api", tags=["query"])
app.include_router(schema.router,  prefix="/api", tags=["schema"])
app.include_router(sources.router, prefix="/api", tags=["sources"])

@app.get("/health")
def health():
    return {"status": "ok"}
