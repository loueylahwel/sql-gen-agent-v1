# Text-to-SQL Agent v2

Ask natural language questions against **any data source** — plug in a database or upload a CSV and interrogate it in plain English. SQL generation runs on the Groq cloud API (llama-3.3-70b-versatile) — no local model server needed.

## Data sources

| Source | How it's configured | Dialect |
|---|---|---|
| **ClickHouse** | `CLICKHOUSE_*` env vars in `backend/.env` (optional) | ClickHouse |
| **File upload** — CSV, TSV, JSON, JSONL, Parquet, XLSX, XLS | Upload via UI or `POST /api/sources/upload`; loaded into an embedded DuckDB session | DuckDB |
| **SQLite database** — .db, .sqlite, .sqlite3 | Upload via UI or `POST /api/sources/upload` | SQLite |

Multiple files can be added to the **same DuckDB source** (form field `source_id` on upload, or the "Add to an existing DuckDB source" checkbox in the UI) to enable cross-file joins.

**Schema discovery is automatic for every source**: table list, columns with types, **and 2 sample rows per table** (capped at the first 20 columns; skipped for tables wider than 50 columns). Sample rows make generated SQL dramatically better for unknown data.

The LLM prompt is **per-dialect** (`You are an expert {dialect} SQL assistant`) with dialect-specific hints — e.g. SQLite gets "LIKE instead of ILIKE", DuckDB gets "tables already exist as views, no read_csv_auto needed". The safety validator (SELECT-only, single statement, blocked keywords) applies to **all** sources.

```
text2sql/
├── backend/                   # FastAPI
│   ├── app/
│   │   ├── main.py            # entrypoint (Text-to-SQL Agent v2)
│   │   ├── api/
│   │   │   ├── query.py       # POST /api/query (with self-correction retry)
│   │   │   ├── schema.py      # GET  /api/schema[?source_id=]
│   │   │   └── sources.py     # GET/POST/DELETE /api/sources (uploads)
│   │   ├── core/
│   │   │   ├── config.py      # settings from .env
│   │   │   ├── llm.py         # Groq client + per-dialect prompt builders
│   │   │   └── validator.py   # SQL safety check (all sources)
│   │   ├── db/
│   │   │   ├── connection.py  # ClickHouse client (lazy import guard)
│   │   │   ├── introspect.py  # compat wrapper → ClickHouseSource
│   │   │   ├── sources.py     # DataSource abstraction + ClickHouse/DuckDB/SQLite impls
│   │   │   └── registry.py    # in-memory source registry + default resolution
│   │   └── models/
│   │       └── schemas.py     # Pydantic models
│   ├── uploads/               # uploaded files, one dir per source (gitignored)
│   ├── .env                   # your config (not committed)
│   ├── .env.example           # template for .env
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                  # Streamlit
│   ├── app.py                 # main UI (source picker + upload + chat)
│   ├── utils/
│   │   ├── api.py             # HTTP calls to backend
│   │   └── charts.py          # auto chart rendering
│   ├── requirements.txt
│   └── Dockerfile
│
└── docker-compose.yml         # run everything together
```

---

## Setup

```bash
# 1. Create the backend env file
cp backend/.env.example backend/.env

# 2. Edit backend/.env:
#    - GROQ_API_KEY   (get one at https://console.groq.com) — required for querying
#    - CLICKHOUSE_*   (OPTIONAL — only for the built-in ClickHouse source)
```

The app boots fine without ClickHouse and without a Groq key — you get clear error messages at query time instead.

---

## Option A — Run with Docker (recommended)

```bash
docker compose up -d

# Open the UI
open http://localhost:8501
# Backend API docs at http://localhost:8000/docs
```

Uploaded files persist in `./backend/uploads` (bind-mounted into the backend container).

---

## Option B — Run locally without Docker

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

---

## Using it

1. **Upload a file** in the sidebar (CSV, Excel, JSON, Parquet, SQLite .db) — it's registered as a source and becomes active immediately. The discovered schema (with sample rows) is shown in a preview.
2. **Pick the active source** from the source list (env-configured ClickHouse appears automatically when reachable).
3. **Ask questions** in the chat. The caption under each answer shows which source answered.
4. Optional: check **"Add to an existing DuckDB source"** before uploading to join multiple files in one source.

---

## Configuration (backend/.env)

| Variable             | Default                  | Notes                                             |
|----------------------|--------------------------|---------------------------------------------------|
| `GROQ_API_KEY`       | — (required for queries) | From https://console.groq.com                     |
| `GROQ_MODEL`         | `llama-3.3-70b-versatile`| Any model available on Groq                       |
| `CLICKHOUSE_HOST`    | — (optional)             | Built-in ClickHouse source; omit to run uploads-only |
| `CLICKHOUSE_USER`    | `default`                |                                                   |
| `CLICKHOUSE_PASSWORD`| — (optional)             |                                                   |
| `CLICKHOUSE_SECURE`  | `true`                   | `false` for plain local ClickHouse                |
| `CLICKHOUSE_DATABASE`| `default`                |                                                   |
| `ROW_LIMIT`          | `500`                    | LIMIT added to generated queries                  |

---

## API endpoints

| Method | Path                      | Description                                        |
|--------|---------------------------|----------------------------------------------------|
| POST   | `/api/query`              | NL question → SQL → results (`source_id` optional) |
| GET    | `/api/schema`             | Schema for a source (`?source_id=`, optional)      |
| POST   | `/api/schema/refresh`     | Bust schema cache (`?source_id=` or all)           |
| GET    | `/api/sources`            | List registered sources + dialects + tables        |
| POST   | `/api/sources/upload`     | Upload a file (multipart `file`, optional `source_id` to add to an existing DuckDB source) |
| DELETE | `/api/sources/{source_id}`| Unregister a source and delete its files           |
| GET    | `/api/health/db`          | Check ClickHouse connection                        |
| GET    | `/docs`                   | Swagger UI                                         |

`source_id` resolution (when omitted on `/api/query` and `/api/schema`): the env ClickHouse source if reachable → otherwise the only registered source → otherwise `400 no data source configured`.

Upload rules: max 100 MB per file (`413`), extensions dispatched by type — `.csv/.tsv/.json/.jsonl/.parquet/.xlsx/.xls` → DuckDB, `.db/.sqlite/.sqlite3` → SQLite, anything else → `415`.

---

## How it works

1. The active source's discovered schema (DDL + sample rows) and the question are sent to Groq with a per-dialect prompt, which returns a SELECT-only query.
2. The query passes a safety validator (no writes, single statement) — applied to every source.
3. If validation or execution fails, the error is sent back to the model for a fix (up to 3 attempts).
4. Results are summarized in plain English and shown in the UI.
