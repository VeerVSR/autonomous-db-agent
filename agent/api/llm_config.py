import itertools
import os
import re
import time
from threading import Lock

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# loading API keys securely from .env file
load_dotenv()

# How long (in seconds) to bench a Gemini key after it reports quota/rate-limit
# exhaustion, before we're willing to try it again.
GEMINI_KEY_COOLDOWN_SECONDS = int(os.getenv("GEMINI_KEY_COOLDOWN_SECONDS", "60"))

# Ordered fallback list when the primary model returns 503 (high demand)
DEFAULT_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]


def _load_models():
    """Allows overriding fallback order via GEMINI_MODELS in .env if needed."""
    raw = os.getenv("GEMINI_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_MODELS)


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
        self._cooldown_until = {k: 0.0 for k in keys}
        self._cycle = itertools.cycle(range(len(keys)))
        self._lock = Lock()

    def mark_exhausted(self, key, cooldown_seconds=None):
        """Benches a key for a while after it reports quota/rate-limit exhaustion."""
        cooldown_seconds = GEMINI_KEY_COOLDOWN_SECONDS if cooldown_seconds is None else cooldown_seconds
        with self._lock:
            self._cooldown_until[key] = time.time() + cooldown_seconds

    def get_key(self):
        """Returns the next key that isn't currently benched (round-robin)."""
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
    """True if an exception means 'this key is out of quota / rate-limited'."""
    try:
        from google.genai.errors import ClientError
        if isinstance(exc, ClientError) and getattr(exc, "code", None) in (429, 403):
            return True
    except ImportError:
        pass
    text = str(exc).upper()
    return (
        "RESOURCE_EXHAUSTED" in text
        or bool(re.search(r"\b429\b", text))
        or "RATE LIMIT" in text
        or "QUOTA EXCEEDED" in text
        or "EXCEEDED YOUR CURRENT QUOTA" in text
    )


def _is_model_unavailable_error(exc: Exception) -> bool:
    """True when the model is overloaded (503) or unavailable (404),
    so we immediately jump to the next fallback model without freezing."""
    text = str(exc).upper()
    return (
        "503" in text
        or "UNAVAILABLE" in text
        or "HIGH DEMAND" in text
        or "OVERLOADED" in text
        or "404" in text
        or "NOT_FOUND" in text
    )


class ResilientChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """Automatically shifts across fallback Gemini models on 503 high-demand
    errors while preserving LangChain structured outputs and tool calling."""

    fallback_models: list[str] = DEFAULT_MODELS

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        models = self.fallback_models or [self.model]
        last_exc = None
        for model_name in models:
            self.model = model_name
            try:
                return super()._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
            except Exception as exc:
                last_exc = exc
                if _is_model_unavailable_error(exc):
                    continue
                raise
        raise last_exc


def get_llm(api_key=None):
    """Returns a resilient Gemini LLM wrapper with multi-key rotation and
    automatic multi-model fallback on 503 server busy errors."""
    key = api_key or get_gemini_pool().get_key()
    models = _load_models()
    return ResilientChatGoogleGenerativeAI(
        model=models[0],
        fallback_models=models,
        temperature=0,
        api_key=key,
        max_retries=0,
        timeout=15,
    )


def extract_text(response):
    if isinstance(response.content, list):
        return response.content[0]["text"]
    else:
        return response.content
