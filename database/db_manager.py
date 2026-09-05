import sqlite3 # Sqlite module is being imported here
import random
from faker import Faker
fake = Faker()

DEPARTMENTS = [
    ("Sales", "New York"), # Department name paired with City 
    ("Engineering", "San Francisco"),
    ("Marketing", "Chicago"),
    ("Human Resources", "Austin"),
    ("Finance", "Boston"),
]

def build_and_seed_database():
    conn = sqlite3.connect("database/company.db")
    cursor = conn.cursor()

    with open("database/schema.sql", "r") as f:
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

def run_sql_query(sql):
    """Executes a SQL query and returns either the results or the error message, as a string."""
    conn = sqlite3.connect("database/company.db")
    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        return f"SQL Error: {e}"
    finally:
        conn.close()
        
def get_schema_description():
    """Returns the schema.sql file content as a string, so it can be shown to the LLM."""
    with open("database/schema.sql", "r") as f:
        return f.read()
        
if __name__ == "__main__":
    build_and_seed_database()