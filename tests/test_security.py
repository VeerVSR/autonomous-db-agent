import pytest
from database.db_manager import run_sql_query, validate_read_only_sql
from agent.langchain_react.react_agent import is_safe_pandas_filter, resolve_data_source
from tests.conftest import table_counts, Upload

SQL_ATTACKS = [
    "DROP TABLE Sales",
    "DELETE FROM Employees",
    "UPDATE Employees SET Salary=0",
    "INSERT INTO Departments(Dept_Name,Location) VALUES('x','y')",
    "SELECT 1; DROP TABLE Sales",
    "SELECT 1;DELETE FROM Sales",
    "/* hi */ DROP TABLE Sales",
    "-- c\nDROP TABLE Sales",
    "PRAGMA writable_schema=1",
    "ATTACH DATABASE '/tmp/evil.db' AS e",
    "VACUUM",
    "CREATE TABLE x(a)",
    "ALTER TABLE Sales ADD COLUMN z",
    "WITH x AS (SELECT 1) DELETE FROM Sales",
    "WITH x AS (SELECT 1) INSERT INTO Departments(Dept_Name,Location) SELECT 'a','b'",
    "REPLACE INTO Departments VALUES (1,'x','y')",
    "  \n\t drop table Sales",
    "",
    "   ",
]


@pytest.mark.parametrize("q", SQL_ATTACKS)
def test_sql_attack_blocked_and_db_intact(db, q):
    before = table_counts(db)
    out = run_sql_query(q)
    assert isinstance(out, str) and out.startswith("SQL Error"), out
    assert table_counts(db) == before


def test_semicolon_in_string_is_not_an_attack(db):
    assert validate_read_only_sql("select * from Employees where Emp_Name = 'a;b'") is None
    assert isinstance(run_sql_query("select * from Employees where Emp_Name = 'a;b'"), list)


def test_columns_are_named(db):
    rows = run_sql_query("select Dept_Name, count(*) as n from Departments join Employees using(Dept_Id) group by 1")
    assert rows and set(rows[0]) == {"Dept_Name", "n"}


def test_row_cap(db):
    rows = run_sql_query("select * from Sales a, Sales b, Sales c")  # 64,000 rows
    assert len(rows) == 200


def test_readonly_connection_blocks_even_if_validation_bypassed(db):
    import sqlite3
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("delete from Sales")


@pytest.mark.parametrize("expr", [
    "__import__('os').system('id')", "Age.sum() > 1", "df.values", "Age > 1 and exit()",
    "@x > 1", "Age ** 9 ** 9 > 1", "lambda: 1", "[x for x in range(9)]", "Age.__class__",
    "__class__ == 1", "(1).__class__ == 1", "'a'.join('b') == 'a'", "Age > 1; import os",
    "x" * 600, "`a` if 1 else 2", "{1:2}", "f'{1}' == 'a'", "open('/etc/passwd')",
])
def test_ast_blocks(expr):
    assert not is_safe_pandas_filter(expr)


@pytest.mark.parametrize("expr", [
    "`Age` > 30", "Age > 30 and City == 'Paris'", "City in ['Paris','Rome']", "Age > -5",
    "Age * 2 > 50", "not (Age < 20)", "None", "", "`First Name` == 'Ann'",
])
def test_ast_allows(expr):
    assert is_safe_pandas_filter(expr)


def test_upload_path_traversal_is_flattened():
    st, target, name, origin = resolve_data_source(Upload("../../etc/evil.xlsx", b"x"))
    assert name == "evil.xlsx" and origin == "STREAMLIT_UPLOAD"


def test_upload_wrong_extension_ignored(db):
    st, target, name, origin = resolve_data_source(Upload("payload.exe", b"x"))
    assert st == "sql"


@pytest.mark.parametrize("q", [
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c",
    "select count(*) from Sales a,Sales b,Sales c,Sales d,Sales e,Sales f,Sales g,Sales h",
])
def test_runaway_query_is_aborted(db, monkeypatch, q):
    import time
    from database import db_manager
    monkeypatch.setattr(db_manager, "QUERY_TIMEOUT_SECONDS", 1)
    t = time.time()
    out = run_sql_query(q)
    assert isinstance(out, str) and "time limit" in out
    assert time.time() - t < 5
