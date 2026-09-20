from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

class SQLQueryOutput(BaseModel):
    reasoning: str = Field(description="Brief explanation of the query logic")
    sql_query: str = Field(description="A single valid SQLite SELECT query")

class SQLReflectionOutput(BaseModel):
    error_analysis: str = Field(description="Why the previous query failed")
    corrected_query: str = Field(description="The fixed SQLite SELECT query")

generation_prompt = PromptTemplate(
    template="""You are a SQLite expert. Given the schema, write a SELECT query to answer the user's question.

Rules:
1. SELECT queries only.
2. Dates are stored as 'YYYY-MM-DD' strings.
3. Qualify column names (table.column) when joining.

Schema:
{schema}

Question: {user_question}
""",
    input_variables=["schema", "user_question"],
)

reflection_prompt = PromptTemplate(
    template="""Your previous SQLite query failed. Analyze the error against the schema and provide a corrected query.

Schema:
{schema}

Question: {user_question}
Failed Query: {failed_query}
Error: {error_message}
""",
    input_variables=["schema", "user_question", "failed_query", "error_message"],
)
system_prompt = """You are a helpful SQLite assistant for company.db.
1. Use `get_schema` to inspect tables and columns.
2. Use `run_query` to run read-only SELECT queries.
3. If `run_query` returns an error, analyze the error message, correct the SQL, and retry.
4. Answer clearly in plain English based on the returned data."""
