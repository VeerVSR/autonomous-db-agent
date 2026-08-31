python --version



mkdir autonomous-db-agent

cd autonomous-db-agent



python -m venv venv

venv\\Scripts\\Activate.ps1



Press Ctrl+Shift+P

Python: Select Interpreter Pick the one whose path contains venv (something like ./venv/bin/python or .\\venv\\Scripts\\python.exe)



req.txt

***langchain*** --------------------> the agent framework and LLM connectors

***langchain-google-genai*** -------> the agent framework and LLM connectors

***langchain-groq*** ---------------> the agent framework and LLM connectors

***python-dotenv*** ----------------> loads API keys from a .env file instead of hardcoding them

***Faker*** ------------------------> generates realistic fake names/salaries/dates for your database



pip install -r requirements.txt



\_\_init\_\_.py : they're empty marker files that tell Python "treat this folder as an importable package."

