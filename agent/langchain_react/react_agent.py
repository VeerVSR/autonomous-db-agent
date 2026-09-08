from database.db_manager import run_sql_query, get_schema_description
from agent.api.llm_config import get_llm,extract_text

def build_initial_prompt(question,schema):
    prompt = f""" You are a SQL Expert. Given the SQL Schema: {schema} Write one SQL query that answers this question: {question} Return ONLY the raw SQL query, nothing else — no explanation, no markdown formatting."""
    return prompt

def build_correction_prompt(question,schema,failed_sql,error_message):
    prompt = f""" You are a SQL expert, Given the sql error message: {error_message} and failed sql query : {failed_sql} , retry solving the same question : {question} Given the sql schema : {schema}"""
    return prompt

def answer_question(question , max_attempts = 4):
    schema = get_schema_description()
    prompt = build_initial_prompt(question,schema)
    
    attempts = 0 
    while attempts<max_attempts:
        attempts+=1
        
        llm = get_llm("gemini")
        response = llm.invoke(prompt)
        generated_sql = extract_text(response)
        
        result = run_sql_query(generated_sql)
        get_llm()
        run_sql_query()
        extract_text()