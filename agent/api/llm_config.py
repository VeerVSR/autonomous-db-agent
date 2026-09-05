import os 
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# loading API keys securely from .env file
load_dotenv()

# the following function which i am creating will provide LLM to the langchain agent. provider can be either 'gemini' or 'groq'.

def get_llm(provider="gemini"):
    if provider == "gemini":
        # The LangChain wrapper of Gemini API
        return ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            temperature=0,
            api_key=os.getenv("GEMINI_API_KEY")

        )
    elif provider == "groq":
        # The LangChain wrapper of Groq API
        return ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0,
            api_key=os.getenv("GROQ_API_KEY")

        )
    else:
        raise ValueError("Invalid provider. Please choose either 'gemini' or 'groq'.")
    

def extract_text(response):
    if isinstance(response.content, list):
        return response.content[0]['text']
    else:
        return response.content
