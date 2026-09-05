import os
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from agent.api.llm_config import get_llm

# 1.Establishing a connection with the database
db_path = "database/company.db"
if not os.path.exists(db_path):
    print(f"Error: Database file '{db_path}' does not exist. Please run the database seeding script first.")
else:
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
    print("Database successfully connected!")
    print("Tables in DB:", db.get_usable_table_names())

    # 2. loading our verified Gemnini LLM
    llm = get_llm("gemini")

    # 3. creating a SQL agent of Langachain( with ReAct framework)
    agent_executor = create_sql_agent(llm, db=db, verbose=True)

    #4. Running a test language query 
    print("\n=== Running a test query ===")
    query = "How many total employees are there in the company?"

    response = agent_executor.invoke({"input": query})
    print("\nFinal Agent Response:")
    print(response["output"])

