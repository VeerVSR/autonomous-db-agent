import os
import sqlite3
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain.agents import create_agent

from agent.langchain_react.prompt import system_prompt

load_dotenv()
DB_PATH = "database/company.db"


@tool
def get_schema() -> str:
    """Get the database tables and columns schema."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cur.fetchall()
    conn.close()
    return "\n".join(t[0] for t in tables if t[0])


@tool
def run_query(query: str) -> str:
    """Execute a SQL SELECT query against company.db and return rows or error."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(query)
        rows = cur.fetchall()
        return str(rows)
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)

agent = create_agent(
    model=llm,
    tools=[get_schema, run_query],
    system_prompt=system_prompt
)


def run_agent(question: str) -> str:
    response = agent.invoke({
        "messages": [
            {"role": "user", "content": question}
        ]
    })
    return response["messages"][-1].content