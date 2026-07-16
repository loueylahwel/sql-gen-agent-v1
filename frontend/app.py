import os
import streamlit as st
import pandas as pd
import requests
from utils.api import (
    query_api, fetch_schema, refresh_schema, fetch_sources, upload_file, check_health,
)
from utils.charts import render_chart

UPLOAD_TYPES = ["csv", "tsv", "json", "jsonl", "parquet", "xlsx", "xls", "db", "sqlite", "sqlite3"]
DIALECT_BADGES = {"ClickHouse": "🏠 ClickHouse", "DuckDB": "📄 DuckDB", "SQLite": "🗄 SQLite"}

st.set_page_config(page_title="Text-to-SQL Agent v2", page_icon="⚡", layout="wide")
st.title("Text-to-SQL Agent v2")
st.caption("Plug in a database or upload a CSV and interrogate it in plain English. Powered by Groq (llama-3.3-70b-versatile).")

with st.sidebar:
    st.header("Settings")
    api_url = st.text_input("Backend URL", value=os.environ.get("BACKEND_URL", "http://localhost:8000"))

    if st.button("Check connection"):
        health = check_health(api_url)
        if health.get("clickhouse") == "ok":
            st.success("ClickHouse connected")
        else:
            st.error("ClickHouse unreachable")

    st.divider()
    st.header("Data sources")

    if "sources" not in st.session_state or st.button("Refresh sources"):
        st.session_state["sources"] = fetch_sources(api_url)
    sources = st.session_state["sources"]

    if sources:
        labels = [f"{s['name']} · {DIALECT_BADGES.get(s['dialect'], s['dialect'])}" for s in sources]
        active = st.session_state.get("active_source")
        current = next((i for i, s in enumerate(sources) if active and s["source_id"] == active["source_id"]), 0)
        choice = st.radio("Active source", range(len(sources)), format_func=lambda i: labels[i], index=current)
        st.session_state["active_source"] = sources[choice]
        active = st.session_state["active_source"]

        tables = active.get("tables", [])
        st.markdown(f"**Tables ({len(tables)}):**")
        for t in tables:
            st.markdown(f"  - `{t}`")

        if st.button("Refresh schema"):
            refresh_schema(api_url, active["source_id"])
            with st.spinner("Fetching schema..."):
                st.session_state["schema"] = fetch_schema(api_url, active["source_id"])
            st.session_state["sources"] = fetch_sources(api_url)
            st.rerun()

        if st.session_state.get("schema"):
            with st.expander("View schema"):
                st.code(st.session_state["schema"].get("ddl", ""), language="sql")
    else:
        st.info("No data sources yet. Upload a file below, or configure ClickHouse in backend/.env.")

    st.subheader("Upload a file")
    st.caption("CSV, TSV, JSON, Parquet, Excel, or a SQLite .db — queryable immediately.")
    uploaded = st.file_uploader("Choose a file", type=UPLOAD_TYPES, label_visibility="collapsed")

    duck_sources = [s for s in sources if s["dialect"] == "DuckDB"]
    target_id = None
    if duck_sources:
        if st.checkbox("Add to an existing DuckDB source (multi-file joins)"):
            target = st.selectbox(
                "DuckDB source", duck_sources, format_func=lambda s: s["name"]
            )
            target_id = target["source_id"] if target else None

    if uploaded is not None and st.button("Upload & register"):
        with st.spinner(f"Loading {uploaded.name}..."):
            result = upload_file(api_url, uploaded.name, uploaded.getvalue(), target_id)
        if "error" in result:
            st.error(f"Upload failed: {result.get('detail', result['error'])}")
        else:
            st.success(f"Registered `{result['name']}` ({result['dialect']})")
            with st.expander("Discovered schema (preview)", expanded=True):
                st.text(result.get("schema_preview", ""))
            st.session_state["sources"] = fetch_sources(api_url)
            st.session_state["active_source"] = next(
                (s for s in st.session_state["sources"] if s["source_id"] == result["source_id"]),
                st.session_state["sources"][0] if st.session_state["sources"] else None,
            )
            st.session_state.pop("schema", None)
            st.rerun()

if "history" not in st.session_state:
    st.session_state["history"] = []

question = st.chat_input("Ask a question about your data…")

if question:
    active = st.session_state.get("active_source")
    st.session_state["history"].append({"role": "user", "content": question})
    with st.spinner("Thinking…"):
        result = query_api(api_url, question, active["source_id"] if active else None)
    if "error" in result:
        st.session_state["history"].append({
            "role": "error",
            "content": result["error"],
            "detail": result.get("detail", ""),
        })
    else:
        st.session_state["history"].append({
            "role": "assistant",
            "content": result,
        })

# detect if user is asking for a chart
CHART_KEYWORDS = ["chart", "plot", "graph", "visualize", "visualise", "show me a", "bar", "line", "pie"]

for msg in reversed(st.session_state["history"]):
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])

    elif msg["role"] == "error":
        with st.chat_message("assistant"):
            st.error(f"**Error:** {msg['content']}")
            if msg.get("detail"):
                st.caption(msg["detail"])

    elif msg["role"] == "assistant":
        data = msg["content"]
        with st.chat_message("assistant"):

            # ── Natural language answer (main response) ──────────────────
            st.markdown(data.get("answer", ""))

            # ── SQL (collapsed by default) ───────────────────────────────
            with st.expander("View SQL", expanded=False):
                st.code(data["sql"], language="sql")

            source_label = data.get("source_name") or data.get("source_id") or "default"
            st.caption(f"↳ {data['row_count']} rows returned · source: {source_label}")

            if data["rows"]:
                df = pd.DataFrame(data["rows"], columns=data["columns"])

                # ── Chart only if user asked for one ─────────────────────
                question_lower = data["question"].lower()
                wants_chart = any(k in question_lower for k in CHART_KEYWORDS)

                if wants_chart:
                    render_chart(df, "Auto")

                # ── Raw data table (always available, collapsed) ─────────
                with st.expander("Raw data"):
                    st.dataframe(df, use_container_width=True)
