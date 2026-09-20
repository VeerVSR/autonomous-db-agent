import ast
import io
import os
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from groq import BadRequestError, GroqError
from langchain_groq import ChatGroq
import pandas as pd

from agent.langchain_react.prompt import (
    ExcelQueryOutput,
    ExcelReflectionOutput,
    RunAgentResult,
    SQLQueryOutput,
    SQLReflectionOutput,
    XAITelemetry,
    excel_generation_prompt,
    excel_reflection_prompt,
    sql_generation_prompt,
    sql_reflection_prompt,
)
from database.db_manager import get_schema_description, run_sql_query
from agent.api.llm_config import get_llm

load_dotenv()

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))

_CHAIN_CACHE: Dict[str, Dict[str, Any]] = {}


def _get_chains(provider: str) -> Dict[str, Any]:
    """Builds (and caches) the LLM chains for a given provider ('groq' or 'gemini')
    so the UI can let the user switch models without restarting the process."""
    if provider not in _CHAIN_CACHE:
        provider_llm = get_llm(provider)
        _CHAIN_CACHE[provider] = {
            "sql_gen": sql_generation_prompt | provider_llm.with_structured_output(SQLQueryOutput),
            "sql_reflect": sql_reflection_prompt | provider_llm.with_structured_output(SQLReflectionOutput),
            "excel_gen": excel_generation_prompt | provider_llm.with_structured_output(ExcelQueryOutput),
            "excel_reflect": excel_reflection_prompt | provider_llm.with_structured_output(ExcelReflectionOutput),
        }
    return _CHAIN_CACHE[provider]


def _extract_sql_from_error(exc: Exception) -> Optional[str]:
    """
    Groq sometimes rejects a response because the model answered in prose
    instead of calling the required structured-output tool -- even when that
    prose contains perfectly correct SQL. Recover it instead of crashing.
    """
    text = str(exc)
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
    else:
        match = re.search(r"(SELECT\s+.*?;)", text, re.DOTALL | re.IGNORECASE)
        sql = match.group(1).strip() if match else None
    if sql:
        sql = sql.replace("\\n", " ")
    return sql

def is_safe_pandas_filter(expression: str) -> bool:
    """
    Validates filter expressions via AST whitelist.
    Pre-processes backticks (`Col Name` -> Col_Name) so ast.parse evaluates legitimate pandas syntax safely.
    """
    if not expression or expression.strip().lower() in ["none", ""]:
        return True
    try:
        sanitized_for_ast = re.sub(r"`([^`]+)`", lambda m: re.sub(r"\s+", "_", m.group(1)), expression)
        tree = ast.parse(sanitized_for_ast, mode="eval")
        allowed_nodes = (
            ast.Expression, ast.Compare, ast.BoolOp, ast.BinOp,
            ast.UnaryOp, ast.Name, ast.Constant, ast.Load,
            ast.And, ast.Or, ast.Not,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.In, ast.NotIn
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                return False
        return True
    except Exception:
        return False


def resolve_data_source(
    uploaded_file: Optional[Any] = None,
    prefer_upload: bool = True
) -> Tuple[str, Union[str, io.BytesIO], str, str]:
    """Resolves data source and origin, preventing directory traversal."""
    if prefer_upload and uploaded_file is not None:
        raw_name = getattr(uploaded_file, "name", "uploaded_file")
        safe_name = os.path.basename(raw_name)

        if safe_name.endswith((".xlsx", ".xls")):
            return "excel", io.BytesIO(uploaded_file.getvalue()), safe_name, "STREAMLIT_UPLOAD"

    if os.path.exists(DB_DIR):
        excel_files = [f for f in os.listdir(DB_DIR) if f.endswith((".xlsx", ".xls")) and not f.startswith("~$")]
        if excel_files:
            safe_excel = os.path.basename(excel_files[0])
            return "excel", os.path.join(DB_DIR, safe_excel), safe_excel, "LOCAL_REPO"

    return "sql", os.path.join(DB_DIR, "company.db"), "company.db", "LOCAL_REPO"


def get_excel_metadata(source: Union[str, io.BytesIO]) -> dict:
    try:
        xl = pd.ExcelFile(source)
        meta = {}
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, nrows=2)
            meta[sheet] = list(df.columns)
        return meta
    except Exception as e:
        return {"error": str(e)}


def run_excel_query(
    source: Union[str, io.BytesIO],
    sheet_name: str,
    query_expr: Optional[str] = None,
    columns: Optional[List[str]] = None,
) -> list:
    try:
        xl = pd.ExcelFile(source)
        if sheet_name not in xl.sheet_names:
            return [{"error": f"Worksheet '{sheet_name}' not found. Available sheets: {xl.sheet_names}"}]

        if query_expr and str(query_expr).strip().lower() not in ["none", ""]:
            if not is_safe_pandas_filter(query_expr):
                return [{"error": f"Security Error: Expression '{query_expr}' failed AST validation."}]

        df = pd.read_excel(source, sheet_name=sheet_name)

        if query_expr and str(query_expr).strip().lower() not in ["none", ""]:
            df = df.query(query_expr)

        if columns:
            valid_cols = [c for c in columns if c in df.columns]
            if not valid_cols:
                return [{"error": f"None of requested columns {columns} exist in sheet '{sheet_name}'. Available: {list(df.columns)}"}]
            df = df[valid_cols]

        return df.head(15).to_dict(orient="records")
    except Exception as e:
        return [{"error": f"Pandas execution error: {str(e)}"}]


def render_xai_tree(xai: Dict[str, Any]) -> str:
    lines = [
        "+-- [EXPLAINABLE AI TELEMETRY]",
        f"|   +-- Origin        : {xai['origin']}",
        f"|   +-- Source        : {xai['source_type']} ({xai['filename']})",
        f"|   +-- Entity Target : {xai['target_entity']}",
        f"|   +-- Confidence    : {xai['confidence']}",
        f"|   +-- Rationale     : {xai['reasoning']}",
    ]
    corrections = xai.get("corrections", [])
    if corrections:
        lines.append("|   +-- Self-Healing Audit:")
        for fix in corrections:
            lines.append(f"|   |   +-- Attempt #{fix['attempt']} Error: {fix['error']}")
            lines.append(f"|   |   +-- Root Cause: {fix['root_cause']}")
            lines.append(f"|   |   +-- Fix Applied: {fix['fix']}")
    else:
        lines.append("|   +-- Self-Healing Audit: 0 Retries (Success on attempt 1)")
    lines.append(f"+-- Returned Records  : {xai['rows_returned']} rows")
    return "\n".join(lines)


def _not_a_sql_question_result(question: str, origin: str, filename: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Built when the question genuinely isn't answerable with a single SQL query
    (e.g. 'brief me about the database'), no SQL could be recovered either, or the
    LLM API call itself failed (bad key, rate limit, connectivity, etc.)."""
    reasoning = note or "Question is not answerable with a SQL query."
    default_answer = (
        "This looks like a question about the database itself rather than its data. "
        "Try asking something like 'how many employees are in Marketing?'"
    )
    return {
        "question": question,
        "source_type": "sql",
        "origin": origin,
        "filename": filename,
        "executed_expression": None,
        "data": None,
        "xai": {
            "source_type": "SQL", "origin": origin, "filename": filename,
            "target_entity": "N/A", "confidence": "N/A",
            "reasoning": reasoning,
            "assumptions": [], "corrections": [], "rows_returned": 0,
        },
        "xai_visual": f"+-- [EXPLAINABLE AI TELEMETRY]\n+-- Note: {reasoning}",
        "answer": note or default_answer,
    }


_CHITCHAT = {
    "thanks", "thank you", "thanks!", "thank you!", "thx", "ty",
    "hi", "hello", "hey", "hii", "yo",
    "ok", "okay", "cool", "nice", "great", "good",
    "bye", "goodbye", "see you", "good morning", "good evening", "good night",
}


def _is_chitchat(question: str) -> bool:
    """Cheap heuristic so greetings/thanks don't get sent to the LLM as a data question."""
    normalized = question.strip().lower().strip("!.? ")
    return normalized in _CHITCHAT


def run_agent(
    question: str,
    uploaded_file: Optional[Any] = None,
    prefer_upload: bool = True,
    max_retries: int = 2,
    provider: str = "groq",
) -> Dict[str, Any]:
    source_type, source_target, filename, origin = resolve_data_source(uploaded_file, prefer_upload=prefer_upload)
    chains = _get_chains(provider)

    if _is_chitchat(question):
        return _not_a_sql_question_result(
            question, origin, filename,
            note="That's just a greeting, not a question about the data -- nothing to query.",
        )
    corrections = []
    res = None

    if source_type == "sql":
        schema = get_schema_description()

        try:
            gen: SQLQueryOutput = chains["sql_gen"].invoke({"schema": schema, "user_question": question})
        except BadRequestError as e:
            recovered_sql = _extract_sql_from_error(e)
            if not recovered_sql:
                return _not_a_sql_question_result(question, origin, filename)
            gen = SimpleNamespace(
                sql_query=recovered_sql,
                reasoning="Recovered SQL from a malformed tool-call response.",
                assumptions=[],
            )
        except GroqError as e:
            # Auth failures, rate limits, connectivity issues, etc. -- fail gracefully
            # instead of crashing the whole app with an unhandled traceback.
            return _not_a_sql_question_result(
                question, origin, filename,
                note=f"The language model API call failed: {e}",
            )
        except Exception as e:
            # Provider-agnostic safety net (e.g. Gemini/Google API errors), so a
            # bad key or quota limit on ANY provider shows a message instead of a crash.
            return _not_a_sql_question_result(
                question, origin, filename,
                note=f"The language model API call failed: {e}",
            )

        current_expr = gen.sql_query
        target_entity = "SQLite Database Tables"
        current_reasoning = gen.reasoning
        assumptions = gen.assumptions

        for attempt in range(1, max_retries + 2):
            res = run_sql_query(current_expr)

            # Robust check handles dict errors, string errors, and raw driver failures
            is_err = (isinstance(res, dict) and "error" in res) or (isinstance(res, str) and "SQL Error" in res)

            if not is_err or attempt > max_retries:
                break

            err_msg = res["error"] if isinstance(res, dict) else str(res)

            try:
                fix: SQLReflectionOutput = chains["sql_reflect"].invoke({
                    "schema": schema,
                    "user_question": question,
                    "failed_query": current_expr,
                    "error_message": err_msg,
                })
            except BadRequestError as e:
                recovered_sql = _extract_sql_from_error(e)
                if not recovered_sql:
                    # Can't recover a corrected query -- stop retrying, report the last real error.
                    break
                fix = SimpleNamespace(
                    corrected_query=recovered_sql,
                    error_analysis="N/A (recovered from malformed tool-call response)",
                    fix_rationale="Recovered corrected SQL from raw model output.",
                )
            except (GroqError, Exception):
                # Auth failures, rate limits, connectivity issues, etc. (any provider) --
                # stop retrying and report the last real SQL error instead of crashing.
                break

            corrections.append({
                "attempt": attempt,
                "error": err_msg,
                "root_cause": fix.error_analysis,
                "fix": fix.fix_rationale,
            })
            current_expr = fix.corrected_query
            current_reasoning = fix.fix_rationale

    else:
        schema = get_excel_metadata(source_target)
        gen: ExcelQueryOutput = chains["excel_gen"].invoke({"excel_metadata": str(schema), "user_question": question})
        current_expr = gen.filter_expression or "None"
        target_sheet = gen.target_sheet
        target_entity = target_sheet
        cols = gen.columns_to_retrieve
        current_reasoning = gen.reasoning
        assumptions = gen.assumptions

        for attempt in range(1, max_retries + 2):
            if isinstance(source_target, io.BytesIO):
                source_target.seek(0)

            res = run_excel_query(source_target, target_sheet, current_expr, cols)
            is_err = isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict) and "error" in res[0]

            if not is_err or attempt > max_retries:
                break

            err_msg = res[0]["error"]
            fix: ExcelReflectionOutput = chains["excel_reflect"].invoke({
                "excel_metadata": str(schema),
                "user_question": question,
                "failed_sheet": target_sheet,
                "failed_filter": str(current_expr),
                "failed_columns": str(cols),
                "error_message": err_msg,
            })

            corrections.append({
                "attempt": attempt,
                "error": err_msg,
                "root_cause": fix.error_analysis,
                "fix": fix.fix_rationale,
            })

            target_sheet = fix.corrected_sheet
            target_entity = target_sheet
            current_expr = fix.corrected_filter_expression or "None"
            cols = fix.corrected_columns or cols
            current_reasoning = fix.fix_rationale

    has_err = (isinstance(res, dict) and "error" in res) or (
        isinstance(res, str) and "SQL Error" in res
    ) or (
        isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict) and "error" in res[0]
    )
    row_count = len(res) if isinstance(res, list) and not has_err else (1 if res and not has_err else 0)

    if has_err:
        confidence = "Failed"
    elif not corrections and row_count > 0:
        confidence = "High"
    elif corrections and row_count > 0:
        confidence = "Medium"
    else:
        confidence = "Low (Zero Rows Match)"

    xai_data = {
        "source_type": source_type.upper(),
        "origin": origin,
        "filename": filename,
        "target_entity": target_entity,
        "confidence": confidence,
        "reasoning": current_reasoning,
        "assumptions": assumptions,
        "corrections": corrections,
        "rows_returned": row_count,
    }

    result = {
        "question": question,
        "source_type": source_type,
        "origin": origin,
        "filename": filename,
        "executed_expression": current_expr,
        "data": res,
        "xai": xai_data,
        "xai_visual": render_xai_tree(xai_data),
    }

    return RunAgentResult(**result).model_dump()