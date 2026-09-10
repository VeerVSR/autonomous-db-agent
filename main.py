import os 
from database.db_manager import build_and_seed_database
from agent.langchain_react.react_agent import run_agent

if not os.path.exists("database/company.db"):
    print("No database found, building one now...")
    build_and_seed_database()
    
while True:
    question = input("Ask a question : ")
    if(question == "exit"):
        break
    else:
        print(run_agent(question))
