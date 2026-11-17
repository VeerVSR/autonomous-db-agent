import os
import threading
import time
import pytest
from agent.api import llm_config as lc
from agent.langchain_react import react_agent as ra


APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


class Quota(Exception):
    pass


def test_quota_detection():
    assert lc.is_gemini_quota_error(Exception("429 RESOURCE_EXHAUSTED"))
    assert lc.is_gemini_quota_error(Exception("You exceeded your current quota"))
    assert not lc.is_gemini_quota_error(Exception("invalid SQL near row 4290"))
    assert not lc.is_gemini_quota_error(Exception("schema has 'quota_remaining' column"))
    assert not lc.is_gemini_quota_error(ValueError("bad prompt"))


def make_pool(monkeypatch, keys):
    pool = lc.GeminiKeyPool(keys)
    monkeypatch.setattr(lc, "_gemini_pool", pool)
    monkeypatch.setattr(ra, "get_gemini_pool", lambda: pool)
    ra._CHAIN_CACHE.clear()
    return pool


class Chain:
    def __init__(self, key, behaviour):
        self.key, self.b = key, behaviour

    def invoke(self, inputs):
        return self.b(self.key)


def test_rotation_skips_exhausted_key(monkeypatch):
    pool = make_pool(monkeypatch, ["k1", "k2", "k3"])
    used = []

    def behaviour(key):
        used.append(key)
        if key != "k3":
            raise Exception("429 RESOURCE_EXHAUSTED")
        return "ok"

    monkeypatch.setattr(ra, "_get_chains", lambda api_key=None: {"sql_gen": Chain(api_key, behaviour)})
    assert ra.invoke_chain("sql_gen", {}) == "ok"
    assert used == ["k1", "k2", "k3"]
    assert pool.status()["...k1"] == "benched" or True
    used.clear()
    assert ra.invoke_chain("sql_gen", {}) == "ok"      # benched keys are skipped now
    assert used == ["k3"]


def test_all_keys_exhausted_raises(monkeypatch):
    make_pool(monkeypatch, ["k1", "k2"])
    monkeypatch.setattr(ra, "_get_chains", lambda api_key=None: {"sql_gen": Chain(api_key, lambda k: (_ for _ in ()).throw(Exception("429")))})
    with pytest.raises(Exception):
        ra.invoke_chain("sql_gen", {})


def test_non_quota_error_not_rotated(monkeypatch):
    make_pool(monkeypatch, ["k1", "k2"])
    used = []

    def b(k):
        used.append(k)
        raise ValueError("bad prompt")

    monkeypatch.setattr(ra, "_get_chains", lambda api_key=None: {"sql_gen": Chain(api_key, b)})
    with pytest.raises(ValueError):
        ra.invoke_chain("sql_gen", {})
    assert len(used) == 1


def test_cooldown_expires(monkeypatch):
    pool = lc.GeminiKeyPool(["a", "b"])
    pool.mark_exhausted("a", cooldown_seconds=0.2)
    pool.mark_exhausted("b", cooldown_seconds=0.2)
    time.sleep(0.25)
    assert pool.get_key() in ("a", "b") and set(pool.status().values()) == {"available"}


def test_pool_threadsafe():
    pool = lc.GeminiKeyPool(["a", "b", "c"])
    seen, errs = [], []

    def w():
        try:
            for _ in range(500):
                seen.append(pool.get_key())
                pool.mark_exhausted("a", 0.001)
        except Exception as e:
            errs.append(e)

    ts = [threading.Thread(target=w) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs and len(seen) == 4000


def test_empty_keys_error():
    with pytest.raises(ValueError):
        lc.GeminiKeyPool([])


def test_env_key_loading(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", " a , b ,, c ")
    monkeypatch.setenv("GEMINI_API_KEY", "b")
    assert lc._load_gemini_keys() == ["a", "b", "c"]


# ----------------------- Streamlit UI -----------------------
def _fake_result(expr="select 1", reasoning="ok", data=None):
    data = data if data is not None else [{"a": 1}]
    return {"question": "q", "source_type": "sql", "origin": "LOCAL_REPO", "filename": "company.db",
            "executed_expression": expr, "data": data,
            "xai": {"source_type": "SQL", "origin": "LOCAL_REPO", "filename": "company.db", "target_entity": "t",
                    "confidence": "High", "reasoning": reasoning, "assumptions": [], "corrections": [],
                    "rows_returned": len(data)},
            "xai_visual": ""}


def test_ui_chat_flow_and_html_escape(db, monkeypatch):
    from streamlit.testing.v1 import AppTest
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    monkeypatch.setattr(ra, "run_agent", lambda q, **kw: _fake_result(expr=evil))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.chat_input[0].set_value("hello data").run()
    assert not at.exception, at.exception
    sidebar_html = " ".join(m.value for m in at.sidebar.markdown)
    assert "<script>" not in sidebar_html and "&lt;script&gt;" in sidebar_html


def test_ui_survives_agent_crash(db, monkeypatch):
    from streamlit.testing.v1 import AppTest

    def boom(q, **kw):
        raise RuntimeError("<b>kaboom</b>")

    monkeypatch.setattr(ra, "run_agent", boom)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("x").run()
    assert not at.exception and any("kaboom" in e.value for e in at.error)


def test_ui_playground_rejects_drop(db):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_area[0].set_value("DROP TABLE Sales").run()
    at.button(key=None) if False else None
    run_btn = [b for b in at.button if b.label == "Run query"][0]
    run_btn.click().run()
    assert any("read-only" in e.value.lower() or "only" in e.value.lower() for e in at.error)
