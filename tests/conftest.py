import io
import os
import sys
import types

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_manager
from agent.langchain_react import react_agent


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Fresh seeded DB in a temp dir; module globals redirected to it."""
    path = str(tmp_path / "company.db")
    monkeypatch.setattr(db_manager, "DB_PATH", path)
    monkeypatch.setattr(react_agent, "DB_DIR", str(tmp_path))
    db_manager.build_and_seed_database()
    return path


def table_counts(path):
    import sqlite3
    c = sqlite3.connect(path)
    out = {t: c.execute(f"select count(*) from {t}").fetchone()[0] for t in ("Departments", "Employees", "Sales")}
    c.close()
    return out


class FakeLLM:
    """Scripted stand-in for invoke_chain. Each chain name maps to a list of
    responses (objects or Exceptions) consumed in order; the last one repeats."""

    def __init__(self, **script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def __call__(self, chain_name, inputs):
        self.calls.append((chain_name, inputs))
        seq = self.script[chain_name]
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        return item


def sqlgen(q, reasoning="r", assumptions=None):
    return types.SimpleNamespace(sql_query=q, reasoning=reasoning, assumptions=assumptions or [])


def sqlfix(q):
    return types.SimpleNamespace(corrected_query=q, error_analysis="bad", fix_rationale="fixed")


@pytest.fixture()
def llm(monkeypatch):
    def install(**script):
        f = FakeLLM(**script)
        monkeypatch.setattr(react_agent, "invoke_chain", f)
        return f
    return install


class Upload:
    def __init__(self, name, data):
        self.name, self._d = name, data

    def getvalue(self):
        return self._d


def make_xlsx_bytes():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"First Name": ["Ann", "Bob", "Cy"], "Age": [25, 41, 33], "City": ["Paris", "Rome", "Paris"]}).to_excel(w, "People", index=False)
    return buf.getvalue()
