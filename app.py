"""
Streamlit UI for the Autonomous DB Agent.

Run with:
    streamlit run app.py
"""

import os
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from database.db_manager import build_and_seed_database, get_schema_description, DB_PATH
from agent.langchain_react.react_agent import run_agent

# ------------------------------------------------------------------ #
# Page + one-time DB bootstrap
# ------------------------------------------------------------------ #
st.set_page_config(
    page_title="Autonomous DB Agent",
    page_icon="\U0001F5C4\uFE0F",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not os.path.exists(DB_PATH):
    with st.spinner("No database found, building one now..."):
        build_and_seed_database()

MODELS = {
    "Gemini 3.5 Flash": "gemini",
    "Groq (openai/gpt-oss-120b)": "groq",
}

QUICK_PROMPTS = [
    "Show me all tables",
    "List all employees",
    "Find top 5 departments by sales",
]

# ------------------------------------------------------------------ #
# Styling -- dark theme with cyan/purple accents, matching the reference
# ------------------------------------------------------------------ #
st.markdown(
    """
    <style>
    .stApp { background-color: #0b1220; }
    section[data-testid="stSidebar"] { background-color: #0e1626; border-right: 1px solid #1e2a3f; }
    div[data-testid="stChatMessage"] { background-color: transparent; }

    .adb-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.5rem 0 1rem 0; border-bottom: 1px solid #1e2a3f; margin-bottom: 1rem;
    }
    .adb-title { font-size: 1.4rem; font-weight: 700; color: #e6edf7; margin: 0; }
    .adb-subtitle { font-size: 0.85rem; color: #7d8aa3; margin: 0; }
    .adb-badge {
        display: inline-flex; align-items: center; gap: 6px;
        background: #10231b; color: #4ade80; border: 1px solid #1f4030;
        padding: 4px 10px; border-radius: 8px; font-size: 0.8rem;
    }
    .adb-dot { width: 8px; height: 8px; border-radius: 50%; background: #4ade80; display: inline-block; }

    .adb-card {
        background: #101a2c; border: 1px solid #1e2a3f; border-radius: 10px;
        padding: 12px 16px; margin: 8px 0;
    }
    .adb-card-title { color: #9db1cf; font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; }

    .adb-confidence-high { color: #4ade80; font-weight: 600; }
    .adb-confidence-medium { color: #facc15; font-weight: 600; }
    .adb-confidence-low, .adb-confidence-failed { color: #f87171; font-weight: 600; }

    .trace-step { border-left: 2px solid #1e2a3f; padding: 0 0 16px 14px; margin-left: 6px; position: relative; }
    .trace-step::before {
        content: ""; position: absolute; left: -6px; top: 2px; width: 10px; height: 10px;
        border-radius: 50%; background: var(--dot-color, #38bdf8);
    }
    .trace-label { font-size: 0.75rem; color: var(--dot-color, #38bdf8); font-weight: 700; letter-spacing: 0.03em; }
    .trace-title { color: #e6edf7; font-size: 0.85rem; font-weight: 600; margin: 2px 0; }
    .trace-body { color: #9db1cf; font-size: 0.78rem; }
    .trace-time { color: #5c6a83; font-size: 0.7rem; float: right; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ #
# Session state
# ------------------------------------------------------------------ #
if "messages" not in st.session_state:
    st.session_state.messages = []  # each: {role, content, result, elapsed}
if "trace" not in st.session_state:
    st.session_state.trace = []  # flat list of {kind, title, body, ts, color}
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "uploaded_excel" not in st.session_state:
    st.session_state.uploaded_excel = None


def _confidence_class(confidence: str) -> str:
    key = (confidence or "").split()[0].lower()
    return f"adb-confidence-{key}" if key in ("high", "medium", "low", "failed") else "adb-confidence-medium"


def _push_trace(kind: str, title: str, body: str, color: str) -> None:
    st.session_state.trace.append({
        "kind": kind, "title": title, "body": body,
        "ts": datetime.now().strftime("%H:%M:%S"), "color": color,
    })


def _ask(question: str, provider: str) -> None:
    """Runs the agent for one question and records both the chat message and the trace."""
    st.session_state.messages.append({"role": "user", "content": question})

    _push_trace("Thought", "Analyzing schema",
                "Checking the database schema to understand available tables.", "#38bdf8")

    start = time.time()
    try:
        result = run_agent(
            question,
            uploaded_file=st.session_state.uploaded_excel,
            provider=provider,
            max_retries=st.session_state.get("max_retries", 2),
        )
        error = None
    except Exception as e:  # last-resort safety net for the UI layer
        result = None
        error = str(e)
    elapsed = time.time() - start

    if error:
        st.session_state.messages.append({"role": "assistant", "content": None, "result": None,
                                           "elapsed": elapsed, "error": error})
        _push_trace("Action", "Request failed", error, "#f87171")
        return

    _push_trace("Action", "Running expression", result["executed_expression"] or "(none -- chit-chat / not a data question)", "#a78bfa")
    rows = result["xai"]["rows_returned"]
    _push_trace("Observation", "Data retrieved" if rows else "No rows / not applicable",
                f"Query executed. Retrieved {rows} row(s)." if result["executed_expression"] else result["xai"]["reasoning"],
                "#4ade80")
    _push_trace("Thought", "Generating final answer",
                result["xai"]["reasoning"], "#38bdf8")

    st.session_state.messages.append({
        "role": "assistant", "content": None, "result": result, "elapsed": elapsed, "error": None,
    })


# ------------------------------------------------------------------ #
# Sidebar: ReAct trace
# ------------------------------------------------------------------ #
with st.sidebar:
    top = st.columns([3, 1])
    top[0].markdown("### \U0001F9E9 ReAct Trace")
    if top[1].button("Clear", use_container_width=True):
        st.session_state.trace = []
    st.caption("Thought \u2192 Action \u2192 Observation")
    st.divider()

    if not st.session_state.trace:
        st.caption("Ask a question to see the reasoning trace here.")
    for step in st.session_state.trace[::-1][:40]:
        st.markdown(
            f"""
            <div class="trace-step" style="--dot-color:{step['color']}">
                <span class="trace-label">{step['kind'].upper()}</span>
                <span class="trace-time">{step['ts']}</span>
                <div class="trace-title">{step['title']}</div>
                <div class="trace-body">{step['body']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------------ #
# Header
# ------------------------------------------------------------------ #
header_l, header_r = st.columns([3, 2])
with header_l:
    st.markdown(
        """
        <div>
            <p class="adb-title">\U0001F5C4\uFE0F Autonomous DB Agent</p>
            <p class="adb-subtitle">Talk to your database. Get real answers.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with header_r:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"""<div class="adb-badge"><span class="adb-dot"></span> SQLite DB: Connected
            <br/><span style="color:#7d8aa3; font-size:0.7rem;">{os.path.basename(DB_PATH)}</span></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        model_label = st.selectbox("Model", list(MODELS.keys()), label_visibility="collapsed")
        provider = MODELS[model_label]

tab_chat, tab_schema, tab_playground, tab_settings = st.tabs(
    ["\U0001F4AC Chat", "\U0001F5C3\uFE0F Schema", "\U0001F9EA Playground", "\u2699\uFE0F Settings"]
)

# ------------------------------------------------------------------ #
# Chat tab
# ------------------------------------------------------------------ #
with tab_chat:
    st.markdown("#### Chat with your database")
    st.caption("Ask questions in natural language. I'll use ReAct to find the answer.")

    chip_cols = st.columns(len(QUICK_PROMPTS))
    for col, prompt in zip(chip_cols, QUICK_PROMPTS):
        if col.button(prompt, use_container_width=True, key=f"chip_{prompt}"):
            st.session_state.pending_question = prompt

    st.divider()

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
            continue

        with st.chat_message("assistant", avatar="\u2728"):
            if msg.get("error"):
                st.error(f"Something went wrong: {msg['error']}")
                continue

            result = msg["result"]
            xai = result["xai"]

            if result["executed_expression"] is None:
                st.write(xai.get("reasoning") or result.get("answer", "Not answerable as a data query."))
            else:
                st.markdown(f"**{xai['rows_returned']}** row(s) returned.")
                st.caption(xai["reasoning"])

                with st.container():
                    st.markdown('<div class="adb-card"><div class="adb-card-title">\U0001F5C4\uFE0F SQL / EXPRESSION</div>', unsafe_allow_html=True)
                    lang = "sql" if result["source_type"] == "sql" else "python"
                    st.code(result["executed_expression"], language=lang)
                    st.markdown("</div>", unsafe_allow_html=True)

                data = result["data"]
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                elif isinstance(data, list) and data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No rows returned.")

                conf_class = _confidence_class(xai["confidence"])
                st.markdown(
                    f'Confidence: <span class="{conf_class}">{xai["confidence"]}</span>'
                    f' &nbsp;|&nbsp; executed in {msg["elapsed"]:.2f}s',
                    unsafe_allow_html=True,
                )

                if xai.get("corrections"):
                    with st.expander(f"Self-healing: {len(xai['corrections'])} retry attempt(s)"):
                        for fix in xai["corrections"]:
                            st.markdown(f"**Attempt #{fix['attempt']}** — {fix['error']}")
                            st.caption(f"Root cause: {fix['root_cause']}")
                            st.caption(f"Fix applied: {fix['fix']}")

    question = st.chat_input("Ask anything about your database...")
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None

    if question:
        with st.spinner("Thinking..."):
            _ask(question, provider)
        st.rerun()

# ------------------------------------------------------------------ #
# Schema tab
# ------------------------------------------------------------------ #
with tab_schema:
    st.markdown("#### Database schema")
    st.caption("This is the exact schema the agent sees when writing SQL.")
    st.code(get_schema_description(), language="sql")

    st.markdown("##### Upload an Excel file instead")
    st.caption("If you upload a spreadsheet, questions will be answered from it instead of the SQL database.")
    uploaded = st.file_uploader("Upload .xlsx", type=["xlsx", "xls"])
    if uploaded is not None:
        st.session_state.uploaded_excel = uploaded
        st.success(f"Using '{uploaded.name}' as the active data source.")
    elif st.session_state.uploaded_excel is not None:
        st.info(f"Currently using uploaded file: {st.session_state.uploaded_excel.name}")
        if st.button("Clear uploaded file, use SQLite DB again"):
            st.session_state.uploaded_excel = None
            st.rerun()

# ------------------------------------------------------------------ #
# Playground tab
# ------------------------------------------------------------------ #
with tab_playground:
    st.markdown("#### SQL Playground")
    st.caption("Run a read-only SELECT query directly, bypassing the LLM.")
    raw_sql = st.text_area("SQL query", value="SELECT * FROM Departments;", height=120)
    if st.button("Run query"):
        from database.db_manager import run_sql_query
        if not raw_sql.strip().lower().startswith("select"):
            st.error("Only SELECT queries are allowed here.")
        else:
            out = run_sql_query(raw_sql)
            if isinstance(out, str):
                st.error(out)
            else:
                st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ #
# Settings tab
# ------------------------------------------------------------------ #
with tab_settings:
    st.markdown("#### Settings")
    st.write(f"**Database path:** `{DB_PATH}`")
    st.write(f"**Active model:** {model_label}")
    max_retries = st.slider("Self-healing retries", 0, 5, 2)
    st.session_state["max_retries"] = max_retries

    if st.button("Rebuild database (wipes existing data)"):
        build_and_seed_database()
        st.success("Database rebuilt with fresh sample data.")

    if st.button("Clear chat history"):
        st.session_state.messages = []
        st.session_state.trace = []
        st.rerun()
