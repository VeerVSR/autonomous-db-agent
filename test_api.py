from agent.api.llm_config import get_llm, get_gemini_pool

print("=== Testing Gemini API ===")
try:
    gemini_llm = get_llm()
    response_gemini = gemini_llm.invoke("Hello! just reply with 'Gemini API is working fine'")
    print("Gemini Response:", response_gemini.content)
except Exception as e:
    print("Gemini error:", e)

print("\n=== Testing each configured Gemini key ===")
pool = get_gemini_pool()
print(f"{pool.key_count()} key(s) configured.")
for key in pool._keys:
    try:
        llm = get_llm(api_key=key)
        response = llm.invoke("Reply with just 'ok'")
        print(f"...{key[-6:]}: OK -> {response.content!r}")
    except Exception as e:
        print(f"...{key[-6:]}: FAILED -> {e}")
