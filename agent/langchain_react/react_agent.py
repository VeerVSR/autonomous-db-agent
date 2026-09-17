import ast
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from dotenv import load_dotenv
from langchain_groq import ChatGroq

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

import pandas as pd

load_dotenv()

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))[cite: 1]

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

sql_gen_chain = sql_generation_prompt | llm.with_structured_output(SQLQueryOutput)
sql_reflect_chain = sql_reflection_prompt | llm.with_structured_output(SQLReflectionOutput)
excel_gen_chain = excel_generation_prompt | llm.with_structured_output(ExcelQueryOutput)
excel_reflect_chain = excel_reflection_prompt | llm.with_structured_output(ExcelReflectionOutput)


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
        elif safe_name.endswith((".db", ".sqlite")):
            temp_db = os.path.join(DB_DIR, safe_name)
            with open(temp_db, "wb") as f:
                f.write(uploaded_file.getvalue())
            return "sql", temp_db, safe_name, "STREAMLIT_UPLOAD"

    if os.path.exists(DB_DIR):
        excel_files = [f for f in os.listdir(DB_DIR) if f.endswith((".xlsx", ".xls")) and not f.startswith("~$")]
        if excel_files:
            safe_excel = os.path.basename(excel_files[0])
            return "excel", os.path.join(DB_DIR, safe_excel), safe_excel, "LOCAL_REPO"

    return "sql", os.path.join(DB_DIR, "company.db"), "company.db", "LOCAL_REPO"[cite: 1]


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
        "┌── [EXPLAINABLE AI TELEMETRY]",
        f"│   ├── Origin        : {xai['origin']}",
        f"│   ├── Source        : {xai['source_type']} ({xai['filename']})",
        f"│   ├── Entity Target : {xai['target_entity']}",
        f"│   ├── Confidence    : {xai['confidence']}",
        f"│   ├── Rationale     : {xai['reasoning']}",
    ]
    corrections = xai.get("corrections", [])
    if corrections:
        lines.append("│   ├── Self-Healing Audit:")
        for fix in corrections:
            lines.append(f"│   │   ├── Attempt #{fix['attempt']} Error: {fix['error']}")
            lines.append(f"│   │   ├── Root Cause: {fix['root_cause']}")
            lines.append(f"│   │   └── Fix Applied: {fix['fix']}")
    else:
        lines.append("│   ├── Self-Healing Audit: 0 Retries (Success on attempt 1)")
    lines.append(f"└── Returned Records  : {xai['rows_returned']} rows")
    return "\n".join(lines)


def run_agent(
    question: str,
    uploaded_file: Optional[Any] = None,
    prefer_upload: bool = True,
    max_retries: int = 2,
) -> Dict[str, Any]:
    source_type, source_target, filename, origin = resolve_data_source(uploaded_file, prefer_upload=prefer_upload)
    corrections = []
    res = None

    if source_type == "sql":
        db_path = source_target if isinstance(source_target, str) else os.path.join(DB_DIR, "company.db")[cite: 1]
        schema = get_schema_description(db_path=db_path)
        gen: SQLQueryOutput = sql_gen_chain.invoke({"schema": schema, "user_question": question})
        current_expr = gen.sql_query
        target_entity = "SQLite Database Tables"
        current_reasoning = gen.reasoning
        assumptions = gen.assumptions

        for attempt in range(1, max_retries + 2):
            res = run_sql_query(current_expr, db_path=db_path)
            
            # Robust check handles dict errors, string errors, and raw driver failures
            is_err = (isinstance(res, dict) and "error" in res) or (isinstance(res, str) and "SQL Error" in res)

            if not is_err or attempt > max_retries:
                break

            err_msg = res["error"] if isinstance(res, dict) else str(res)
            fix: SQLReflectionOutput = sql_reflect_chain.invoke({
                "schema": schema,
                "user_question": question,
                "failed_query": current_expr,
                "error_message": err_msg,
            })
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
        gen: ExcelQueryOutput = excel_gen_chain.invoke({"excel_metadata": str(schema), "user_question": question})
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
            fix: ExcelReflectionOutput = excel_reflect_chain.invoke({
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
