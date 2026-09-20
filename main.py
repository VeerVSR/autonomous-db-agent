import os
from database.db_manager import build_and_seed_database, DB_PATH
from agent.langchain_react.react_agent import run_agent

if not os.path.exists(DB_PATH):
    print("No database found, building one now...")
    build_and_seed_database()

while True:
    question = input("Ask a question : ")
    if question.strip().lower() == "exit":
        break

    try:
        result = run_agent(question)
    except Exception as e:
        print(f"\nSomething went wrong while answering that: {e}\n")
        continue

    print(f"\nSQL / expression run : {result['executed_expression']}")
    print(f"Data                 : {result['data']}")
    print(result["xai_visual"])
    print()
