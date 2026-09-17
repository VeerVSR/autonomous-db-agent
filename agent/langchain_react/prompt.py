from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate


# --- Public Contract Schemas ---
class XAITelemetry(BaseModel):
    source_type: str
    origin: str
    filename: str
    target_entity: str
    confidence: str
    reasoning: str
    assumptions: List[str]
    corrections: List[Dict[str, Any]]
    rows_returned: int


class RunAgentResult(BaseModel):
    question: str
    source_type: str
    origin: str
    filename: str
    executed_expression: str
    data: Any
    xai: XAITelemetry
    xai_visual: str


# --- Internal LLM Structured Output Schemas ---
class SQLQueryOutput(BaseModel):
    reasoning: str = Field(description="Step-by-step logic for chosen tables, joins, and filters")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions regarding schema bounds or criteria")
    sql_query: str = Field(description="Valid SQLite SELECT query")


class SQLReflectionOutput(BaseModel):
    error_analysis: str = Field(description="Root cause of why the SQLite execution failed")
    fix_rationale: str = Field(description="Adjustments made to fix the query")
    corrected_query: str = Field(description="The corrected, executable SQLite SELECT query")


class ExcelQueryOutput(BaseModel):
    reasoning: str = Field(description="Step-by-step logic for chosen sheet, filter, and projections")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions regarding Excel columns or values")
    target_sheet: str = Field(description="Target worksheet name to read")
    filter_expression: Optional[str] = Field(default=None, description="Simple pandas condition or None")
    columns_to_retrieve: List[str] = Field(default_factory=list, description="Target columns to fetch")


class ExcelReflectionOutput(BaseModel):
    error_analysis: str = Field(description="Root cause of why the pandas operation failed")
    fix_rationale: str = Field(description="Adjustments made to resolve the error")
    corrected_sheet: str = Field(description="The corrected sheet name")
    corrected_filter_expression: Optional[str] = Field(default=None, description="Corrected pandas filter condition or None")
    corrected_columns: List[str] = Field(default_factory=list, description="Corrected column list based on target sheet")


# --- Prompts ---
sql_generation_prompt = PromptTemplate(
    template="""You are a SQLite specialist. Write a read-only SELECT query.
Rules:
1. SELECT queries only. No DDL/DML.
2. Canonical dates: 'YYYY-MM-DD'.
3. Use only tables and columns from the schema.

Schema:
{schema}

Question: {user_question}
""",
    input_variables=["schema", "user_question"],
)

sql_reflection_prompt = PromptTemplate(
    template="""Your SQLite query failed. Diagnose the error and provide a corrected SELECT query.

Schema:
{schema}

Question: {user_question}
Failed Query: {failed_query}
Engine Error: {error_message}
""",
    input_variables=["schema", "user_question", "failed_query", "error_message"],
)

excel_generation_prompt = PromptTemplate(
    template="""You are an Excel analyst. Select the target sheet, column list, and boolean filter.
Rules:
1. Choose an exact sheet name from the metadata.
2. filter_expression must only use simple comparison operations (e.g. `Age` > 30 and `City` == 'Paris'). Use None for all rows.
3. Wrap column names with spaces in backticks (e.g. `First Name`).
4. Select only columns present in the sheet.

Metadata:
{excel_metadata}

Question: {user_question}
""",
    input_variables=["excel_metadata", "user_question"],
)

excel_reflection_prompt = PromptTemplate(
    template="""Your pandas Excel operation failed.
Review the previous attempted columns, fix the sheet name, filter condition, and reconcile the column list against the available sheet columns.

Metadata:
{excel_metadata}

Question: {user_question}
Failed Sheet: {failed_sheet}
Failed Filter: {failed_filter}
Failed Columns Attempted: {failed_columns}
Error Trace: {error_message}
""",
    input_variables=["excel_metadata", "user_question", "failed_sheet", "failed_filter", "failed_columns", "error_message"],
)
