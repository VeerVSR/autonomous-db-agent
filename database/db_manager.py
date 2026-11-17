import os
import re
import sqlite3 # Sqlite module is being imported here
import time
import random
from faker import Faker
fake = Faker()

# Absolute paths so these functions work regardless of the caller's working directory
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "company.db")
SCHEMA_PATH = os.path.join(DB_DIR, "schema.sql")

DEPARTMENTS = [
    ("Sales", "New York"), # Department name paired with City 
    ("Engineering", "San Francisco"),
    ("Marketing", "Chicago"),
    ("Human Resources", "Austin"),
    ("Finance", "Boston"),
]

def build_and_seed_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()

    cursor.executescript(schema_sql)
    cursor.executemany("INSERT INTO Departments (Dept_Name, Location) VALUES (?, ?)", DEPARTMENTS)

    cursor.execute("SELECT Dept_Id FROM Departments")
    dept_ids = cursor.fetchall()
    employees = []
    for i in range(40):
        name = fake.name()
        dept_id = random.choice(dept_ids)[0]
        salary = fake.pyfloat(min_value=35000, max_value=150000, right_digits=2)
        employees.append((name, dept_id, salary))

    cursor.executemany("INSERT INTO Employees (Emp_Name, Dept_Id, Salary) VALUES (?, ?, ?)", employees)

    cursor.execute("SELECT Emp_Id FROM Employees")
    emp_ids = cursor.fetchall()
    sales = []
    for i in range(40):
        emp_id = random.choice(emp_ids)[0]
        amount = fake.pyfloat(min_value=100, max_value=20000, right_digits=2)
        date = fake.date_between(start_date="-1y", end_date="today").isoformat()
        sales.append((amount, date, emp_id))

    cursor.executemany("INSERT INTO Sales (Amount, Date, Emp_Id) VALUES (?, ?, ?)", sales)

    conn.commit()
    conn.close()

MAX_RESULT_ROWS = 200  # hard cap so a runaway SELECT can't flood the UI / memory
QUERY_TIMEOUT_SECONDS = 5  # runaway queries (recursive CTEs, giant cross joins) are aborted

_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_STRINGS = re.compile(r"'(?:[^']|'')*'")
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def validate_read_only_sql(sql):
    """Returns None if `sql` is a single read-only SELECT/WITH statement,
    otherwise a human-readable reason it was rejected. This is defence layer 1;
    layer 2 is opening SQLite itself in read-only mode (see run_sql_query)."""
    if not isinstance(sql, str) or not sql.strip():
        return "Empty query."
    # Blank out string literals first so ';' or '--' inside 'quoted text' isn't misread.
    cleaned = _STRINGS.sub("''", sql)
    cleaned = _COMMENTS.sub(" ", cleaned).strip().rstrip(";").strip()
    if not _ALLOWED_START.match(cleaned):
        return "Only read-only SELECT queries are allowed."
    if ";" in cleaned:
        return "Multiple statements are not allowed."
    return None


def run_sql_query(sql):
    """Executes a read-only SQL query.
    Returns a list of dicts (column name -> value, capped at MAX_RESULT_ROWS),
    or an error string starting with 'SQL Error'."""
    reason = validate_read_only_sql(sql)
    if reason:
        return f"SQL Error: {reason}"

    # mode=ro: even if validation were bypassed, SQLite refuses every write.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    # Called every ~10k SQLite VM steps; returning non-zero aborts the query.
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(MAX_RESULT_ROWS)
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        if "interrupted" in str(e).lower():
            return f"SQL Error: query exceeded the {QUERY_TIMEOUT_SECONDS}s time limit and was aborted."
        return f"SQL Error: {e}"
    finally:
        conn.close()


def get_schema_description():
    """Returns the schema.sql file content as a string, so it can be shown to the LLM."""
    with open(SCHEMA_PATH, "r") as f:
        return f.read()
        
if __name__ == "__main__":
    build_and_seed_database()