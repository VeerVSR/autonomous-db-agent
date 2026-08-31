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

conn = sqlite3.connect("database/company.db") # here we are creating a connection , opens/creates a DB file
cursor = conn.cursor() # this is used to execute the SQL script 

with open("database/schema.sql","r") as f: # this will oppen the file in read mode
    schema_sql = f.read()  # reads the file content as one big string 

cursor.executescript(schema_sql) # this will run all the blocks having multiple statements
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
    amount =  fake.pyfloat(min_value=100, max_value=20000, right_digits=2)
    date = fake.date_between(start_date="-1y", end_date="today").isoformat()
    sales.append((amount,date,emp_id))

cursor.executemany("INSERT INTO Sales (Amount, Date, Emp_Id) VALUES (?, ?, ?)", sales)

conn.commit() # telling that we have made and saved the changes in the file
conn.close() #closing file to prevent any other changes automatically