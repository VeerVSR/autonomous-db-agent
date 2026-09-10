import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain.agents import create_agent

from agent.langchain_react.prompt import system_prompt
from database.db_manager import get_schema_description, run_sql_query

load_dotenv()


@tool
def get_schema() -> str:
    """Get the database tables and columns schema."""
    return get_schema_description()


@tool
def run_query(query: str) -> str:
    """Execute a SQL SELECT query against company.db and return rows or error."""
    result = run_sql_query(query)
    return str(result)


llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0
)

agent = create_agent(
    model=llm,
    tools=[get_schema, run_query],
    system_prompt=system_prompt,
    debug=True
)


def run_agent(question: str) -> str:
    response = agent.invoke({
        "messages": [
            {"role": "user", "content": question}
        ]
    })
    return response["messages"][-1].content