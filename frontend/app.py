import os

import pandas as pd
import streamlit as st
from utils.api import (
    query_api,
    fetch_schema,
    refresh_schema,
    fetch_sources,
    upload_file,
    check_health,
)
from utils.charts import render_chart

UPLOAD_TYPES = ["csv", "tsv", "json", "jsonl", "parquet", "xlsx", "xls", "db", "sqlite", "sqlite3"]
DIALECT_LABELS = {"DuckDB": "DuckDB", "SQLite": "SQLite"}

st.set_page_config(
    page_title="Text-to-SQL Agent v2",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }

    .stApp { background: #0a0f1c; }

    .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 2px; }
    .brand-chip {
        width: 30px; height: 30px; background: #22d3ee; border-radius: 3px;
        display: flex; align-items: center; justify-content: center;
        color: #0a0f1c; font-weight: 900; font-size: 15px;
    }
    .brand-name { color: #fff; font-weight: 700; font-size: 20px; letter-spacing: -0.5px; }
    .tagline { color: #9ca3af; font-size: 13px; margin: 0 0 22px 0; }

    .hero-title {
        color: #fff; font-size: 2.4rem; font-weight: 900; letter-spacing: -1.5px;
        margin: 0; line-height: 1.05;
    }
    .hero-title .accent { color: #22d3ee; }
    .hero-sub { color: #9ca3af; font-size: 1rem; margin: 8px 0 22px 0; }

    .step-badge {
        display: inline-flex; align-items: center; justify-content: center;
        background: #22d3ee; color: #0a0f1c; font-weight: 900; font-size: 13px;
        border-radius: 3px; width: 24px; height: 24px; margin-right: 8px;
    }
    .step-header {
        color: #fff; font-size: 15px; font-weight: 700; letter-spacing: -0.3px;
        margin: 0 0 12px 0; display: flex; align-items: center;
    }
    .explainer-num { color: #22d3ee; font-weight: 900; font-size: 13px; }
    .explainer-title { color: #fff; font-weight: 700; font-size: 14px; margin: 4px 0; }
    .explainer-text { color: #6b7280; font-size: 12px; line-height: 1.5; }
    .muted { color: #6b7280; font-size: 12px; }

    .status-ok { color: #22d3ee; font-weight: 700; }
    .status-fail { color: #f87171; font-weight: 700; }

    .stButton button[kind="primary"],
    .stDownloadButton button[kind="primary"] {
        background: #22d3ee; color: #0a0f1c; border: none; font-weight: 700;
        border-radius: 6px; transition: background 0.15s;
    }
    .stButton button[kind="primary"]:hover,
    .stDownloadButton button[kind="primary"]:hover { background: #67e8f9; }
    .stButton button[kind="secondary"] {
        background: #1f2937; color: #d1d5db; border: 1px solid #374151; border-radius: 6px;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {
        background: #111827; border: 1px solid #1f2937; color: #fff; border-radius: 6px;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #22d3ee; box-shadow: 0 0 0 1px #22d3ee40;
    }
    div[data-baseweb="select"] > div {
        background: #111827; border-color: #1f2937; border-radius: 6px;
    }

    div[data-testid="stMetric"] {
        background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 12px 16px;
    }
    div[data-testid="stMetric"] label { color: #6b7280 !important; font-size: 12px !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #22d3ee !important; }

    div[data-testid="stExpander"] { background: #111827; border: 1px solid #1f2937; border-radius: 8px; }
    div[data-testid="stProgress"] > div > div { background: #22d3ee; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background: #111827; border-radius: 8px; }

    label[data-testid="stWidgetLabel"] p { font-size: 12px; color: #9ca3af; }
    hr { border-color: #1f2937; }
    </style>
    """,
    unsafe_allow_html=True,
)

MODEL_NAME = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _step_header(number, title):
    st.markdown(
        f'<p class="step-header"><span class="step-badge">{number}</span>{title}</p>',
        unsafe_allow_html=True,
    )


def _explainer(number, title, text):
    st.markdown(
        f'<div class="explainer-num">{number}</div>'
        f'<div class="explainer-title">{title}</div>'
        f'<div class="explainer-text">{text}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="brand"><div class="brand-chip">Q</div>'
    '<span class="brand-name">Text-to-SQL Agent v2</span></div>'
    '<p class="tagline">ask your data questions in plain english. any source.</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
if "sources" not in st.session_state:
    st.session_state["sources"] = []
if "history" not in st.session_state:
    st.session_state["history"] = []

api_url = os.environ.get("BACKEND_URL", "http://localhost:8002")

# ---------------------------------------------------------------------------
# Control strip
# ---------------------------------------------------------------------------
with st.container(border=True):
    _step_header(1, "Data source")

api_url = os.environ.get("BACKEND_URL", "http://localhost:8002")

# ---------------------------------------------------------------------------
# Control strip
# ---------------------------------------------------------------------------
with st.container(border=True):
    _step_header(1, "Data source")

    if st.button("Refresh sources", help="Reload the list of registered sources"):
        st.session_state["sources"] = fetch_sources(api_url)

    sources = st.session_state["sources"]

    r1_c1, r1_c2 = st.columns([2, 2], vertical_alignment="bottom")
    with r1_c1:
        if sources:
            labels = [f"{s['name']} · {DIALECT_LABELS.get(s['dialect'], s['dialect'])}" for s in sources]
            index_map = {s["source_id"]: i for i, s in enumerate(sources)}
            active = st.session_state.get("active_source")
            default_index = index_map.get(active["source_id"], 0) if active else 0
            choice = st.selectbox("Active source", range(len(sources)),
                                  format_func=lambda i: labels[i], index=default_index)
            st.session_state["active_source"] = sources[choice]
        else:
            st.markdown('<p class="muted">No sources yet. Upload a file below.</p>', unsafe_allow_html=True)
            st.session_state["active_source"] = None

    with r1_c2:
        uploaded = st.file_uploader("Upload file", type=UPLOAD_TYPES,
                                    help="CSV, TSV, JSON, Parquet, Excel, or a SQLite .db")

    active = st.session_state.get("active_source")
    duck_sources = [s for s in sources if s["dialect"] == "DuckDB"]
    target_id = None
    if duck_sources and uploaded is not None:
        if st.checkbox("Add to an existing DuckDB source for multi-file joins"):
            target = st.selectbox("DuckDB source", duck_sources, format_func=lambda s: s["name"])
            target_id = target["source_id"] if target else None

    if uploaded is not None:
        _, btn_col, _ = st.columns([1, 1, 1])
        with btn_col:
            do_upload = st.button("Upload & register", type="primary", use_container_width=True)
        if do_upload:
            with st.spinner(f"Loading {uploaded.name}..."):
                result = upload_file(api_url, uploaded.name, uploaded.getvalue(), target_id)
            if "error" in result:
                st.error(f"Upload failed: {result.get('detail', result['error'])}")
            else:
                st.success(f"Registered `{result['name']}` ({result['dialect']})")
                st.session_state["sources"] = fetch_sources(api_url)
                st.session_state["active_source"] = next(
                    (s for s in st.session_state["sources"] if s["source_id"] == result["source_id"]),
                    st.session_state["sources"][0] if st.session_state["sources"] else None,
                )
                st.session_state.pop("schema", None)
                st.rerun()

    if active and st.session_state.get("schema"):
        with st.expander("Schema"):
            st.code(st.session_state["schema"].get("ddl", ""), language="sql")

# ---------------------------------------------------------------------------
# Empty state hero
# ---------------------------------------------------------------------------
if not sources:
    st.markdown(
        '<h1 class="hero-title">Ask your data anything.<br><span class="accent">No SQL required.</span></h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="hero-sub">Upload a file to get started. The agent discovers the schema and writes the SQL for you.</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        _explainer("01", "Connect a source", "CSV, Excel, JSON, Parquet, or SQLite — one upload away.")
    with c2:
        _explainer("02", "Ask in plain English", "The agent sees your schema and sample rows, then generates dialect-aware SQL.")
    with c3:
        _explainer("03", "Get SQL + answers", "Results come back with a plain-English summary, the query, and optional charts.")
    st.write("")

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
active = st.session_state.get("active_source")
if active:
    st.divider()
    c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
    with c1:
        _step_header(2, "Ask a question")
    with c2:
        if st.session_state["history"] and st.button("Clear chat", use_container_width=True):
            st.session_state["history"] = []
            st.rerun()

    if not st.session_state["history"]:
        with st.chat_message("assistant"):
            st.markdown(
                "Hi. Ask me anything about this source. For example:\n\n"
                "- What columns are available?\n"
                "- Show the first 10 rows\n"
                "- What is the total by category?\n"
                "- Plot revenue over time"
            )

    question = st.chat_input("Ask a question about your data...")

    if question:
        st.session_state["history"].append({"role": "user", "content": question})
        with st.spinner("Thinking..."):
            result = query_api(api_url, question, active["source_id"])
        if "error" in result:
            st.session_state["history"].append({
                "role": "error",
                "content": result["error"],
                "detail": result.get("detail", ""),
            })
        else:
            st.session_state["history"].append({"role": "assistant", "content": result})

    CHART_KEYWORDS = ["chart", "plot", "graph", "visualize", "visualise", "show me a", "bar", "line", "pie"]

    for msg in st.session_state["history"]:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif msg["role"] == "error":
            with st.chat_message("assistant"):
                detail = msg.get("detail", "")
                if "Rate limit" in detail or "rate limit" in detail:
                    st.error("Rate limit reached")
                    st.markdown(
                        "Your Groq organization hit its daily or per-minute token limit. "
                        "All configured keys share the same org, so rotating keys does not raise the cap.\n\n"
                        "Options:\n"
                        "- Wait a few minutes for the limit to reset\n"
                        "- Upgrade to the Dev Tier at https://console.groq.com/settings/billing\n"
                        "- Add a Groq API key from a different account/organization"
                    )
                else:
                    st.error(f"Error: {msg['content']}")
                    if detail:
                        st.caption(detail)
        elif msg["role"] == "assistant":
            data = msg["content"]
            with st.chat_message("assistant"):
                st.markdown(data.get("answer", ""))
                with st.expander("View SQL"):
                    st.code(data["sql"], language="sql")
                source_label = data.get("source_name") or data.get("source_id") or "default"
                st.caption(f"{data['row_count']} rows · source: {source_label}")

                if data["rows"]:
                    df = pd.DataFrame(data["rows"], columns=data["columns"])
                    if any(k in data["question"].lower() for k in CHART_KEYWORDS):
                        render_chart(df, "Auto")
                    with st.expander("Raw data"):
                        st.dataframe(df, use_container_width=True)


