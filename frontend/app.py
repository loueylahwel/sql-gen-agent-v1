import streamlit as st
import pandas as pd
import requests
from utils.api import query_api, fetch_schema, check_health
from utils.charts import render_chart

st.set_page_config(page_title="Text-to-SQL", page_icon="🦙", layout="wide")
st.title("Text-to-SQL")
st.caption("Ask questions in plain English. Powered by Ollama running locally.")

with st.sidebar:
    st.header("Settings")
    api_url = st.text_input("Backend URL", value="http://backend:8000")

    if st.button("Check connection"):
        health = check_health(api_url)
        if health.get("clickhouse") == "ok":
            st.success("ClickHouse connected")
        else:
            st.error("ClickHouse unreachable")

    st.divider()
    st.header("Schema")
    if st.button("Load / Refresh schema"):
        with st.spinner("Fetching schema..."):
            schema_data = fetch_schema(api_url)
            if schema_data:
                st.session_state["schema"] = schema_data
                st.session_state["tables"] = schema_data.get("tables", [])

    if "tables" in st.session_state:
        st.markdown(f"**Database:** `{st.session_state['schema'].get('database')}`")
        st.markdown(f"**Tables:** {len(st.session_state['tables'])}")
        for t in st.session_state["tables"]:
            st.markdown(f"  - `{t}`")
        with st.expander("View full DDL"):
            st.code(st.session_state["schema"].get("ddl", ""), language="sql")

if "history" not in st.session_state:
    st.session_state["history"] = []

question = st.chat_input("Ask a question about your data…")

if question:
    st.session_state["history"].append({"role": "user", "content": question})
    with st.spinner("Thinking…"):
        result = query_api(api_url, question)
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

            st.caption(f"↳ {data['row_count']} rows returned")

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