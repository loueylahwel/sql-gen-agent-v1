from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import query, schema

app = FastAPI(
    title="Text-to-SQL API",
    description="Natural language to ClickHouse SQL using Groq",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router,  prefix="/api", tags=["query"])
app.include_router(schema.router, prefix="/api", tags=["schema"])

@app.get("/health")
def health():
    return {"status": "ok"}