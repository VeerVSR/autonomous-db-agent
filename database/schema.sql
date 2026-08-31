DROP TABLE IF EXISTS Sales; ---Droping tables each time as we need to create tables again and again during multiple calls 
DROP TABLE IF EXISTS Employees; --- Droping is in reverse order as the sales is dependent on emp and emp dependent on departments
DROP TABLE IF EXISTS Departments;


CREATE TABLE Departments(
    Dept_Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Dept_Name TEXT NOT NULL,
    Location TEXT NOT NULL
);

CREATE TABLE Employees(
    Emp_Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Emp_Name TEXT NOT NULL,
    Dept_Id INTEGER NOT NULL,
    Salary REAL NOT NULL,
    FOREIGN KEY (Dept_Id) REFERENCES Departments(Dept_Id)
);

CREATE TABLE Sales(
    Sale_Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Amount REAL NOT NULL,
    Date TEXT NOT NULL,
    Emp_Id INTEGER NOT NULL,
    FOREIGN KEY (Emp_Id) REFERENCES Employees(Emp_Id)
);