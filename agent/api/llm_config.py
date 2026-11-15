import os 
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# loading API keys securely from .env file
load_dotenv()

# How long (in seconds) to bench a Gemini key after it reports quota/rate-limit
# exhaustion, before we're willing to try it again.
GEMINI_KEY_COOLDOWN_SECONDS = int(os.getenv("GEMINI_KEY_COOLDOWN_SECONDS", "60"))


def _load_gemini_keys():
    """Reads GEMINI_API_KEYS (comma-separated) for multi-key rotation.
    Falls back to the single GEMINI_API_KEY so older .env files still work."""
    keys = []
    raw = os.getenv("GEMINI_API_KEYS", "")
    if raw.strip():
        keys = [k.strip() for k in raw.split(",") if k.strip()]

    single = os.getenv("GEMINI_API_KEY", "").strip()
    if single and single not in keys:
        keys.append(single)

    return keys


class GeminiKeyPool:
    """Round-robins across several Gemini API keys and automatically benches
    any key that comes back exhausted (HTTP 429 quota / rate limit), so the
    agent keeps working as long as at least one key still has quota left."""

    def __init__(self, keys):
        if not keys:
            raise ValueError(
                "No Gemini API keys configured. Set GEMINI_API_KEYS "
                "(comma-separated, e.g. 'key1,key2,key3') or the single "
                "GEMINI_API_KEY in your .env file."
            )
        self._keys = keys
        self._cooldown_until = {k: 0.0 for k in keys}  # key -> unix ts when usable again
        self._cycle = itertools.cycle(range(len(keys)))
        self._lock = Lock()

    def mark_exhausted(self, key, cooldown_seconds=None):
        """Benches a key for a while after it reports quota/rate-limit exhaustion."""
        cooldown_seconds = GEMINI_KEY_COOLDOWN_SECONDS if cooldown_seconds is None else cooldown_seconds
        with self._lock:
            self._cooldown_until[key] = time.time() + cooldown_seconds

    def get_key(self):
        """Returns the next key that isn't currently benched (round-robin).
        If every key is benched, returns whichever will free up soonest
        instead of raising -- the caller still gets to try its luck."""
        with self._lock:
            now = time.time()
            for _ in range(len(self._keys)):
                idx = next(self._cycle)
                key = self._keys[idx]
                if self._cooldown_until[key] <= now:
                    return key
            return min(self._cooldown_until, key=self._cooldown_until.get)

    def key_count(self):
        return len(self._keys)

    def status(self):
        """Handy for debugging: which keys are live vs. benched right now."""
        now = time.time()
        return {
            f"...{k[-6:]}": ("benched" if until > now else "available")
            for k, until in self._cooldown_until.items()
        }


_gemini_pool = None


def get_gemini_pool():
    global _gemini_pool
    if _gemini_pool is None:
        _gemini_pool = GeminiKeyPool(_load_gemini_keys())
    return _gemini_pool


def is_gemini_quota_error(exc: Exception) -> bool:
    """True if an exception from the Gemini API means 'this key is out of
    quota / being rate-limited right now' (as opposed to a real bug, a bad
    prompt, etc.) -- that's the case we want to rotate keys for."""
    try:
        from google.genai.errors import ClientError
        if isinstance(exc, ClientError) and getattr(exc, "code", None) in (429, 403):
            return True
    except ImportError:
        pass
    text = str(exc).upper()
    return "RESOURCE_EXHAUSTED" in text or "429" in text or "QUOTA" in text




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
