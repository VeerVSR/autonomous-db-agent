from agent.api.llm_config import get_llm

print("=== Testing Gemini API ===")
try:
    gemini_llm = get_llm("gemini")
    response_gemini = gemini_llm.invoke("Hello! just reply with 'Gemini API is working fine'")
    print("Gemini Response:", response_gemini.content)
except Exception as e:
    print("Gemini error:", e)

print("\n=== Testing Groq API ===")
try:
    groq_llm = get_llm("groq")
    response_groq = groq_llm.invoke("Hello! just reply with 'Groq API is working fine'")
    print("Groq Response:", response_groq.content)

except Exception as e:
    print("Groq Error:", e)
    