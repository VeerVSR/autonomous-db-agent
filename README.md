# 🗄️ Autonomous DB Agent

An autonomous, self-healing data analysis agent built with **LangChain**, **Streamlit**, and **Google Gemini**.

This project translates natural language questions into executable **SQLite queries** or **Pandas filter expressions** (for Excel spreadsheets), features an automated **Self-Healing Reflection Loop** to recover from execution errors, and provides full **Explainable AI (XAI) Telemetry** for every query run.

---

## ✨ Key Features

* **Dual Data Source Engine (SQL & Excel):** Queries a local SQLite relational database (`company.db`) by default, or dynamically switches to analyzing `.xlsx` / `.xls` spreadsheets uploaded via the Streamlit UI or placed in the `database/` directory.
* **Self-Healing Reflection Loop:** If a generated SQL query or Pandas expression fails during execution, the agent captures the engine traceback, diagnoses the root cause using structured LLM reflection (`SQLReflectionOutput` / `ExcelReflectionOutput`), and automatically retries up to a configurable limit (`max_retries`).
* **Explainable AI (XAI) Telemetry:** Every response returns structured metadata (`XAITelemetry`) and an ASCII visual decision tree detailing the data origin, target entity, confidence score (`High`, `Medium`, `Low`, or `Failed`), step-by-step reasoning, schema assumptions, and a complete self-healing retry audit trail.
* **Multi-Key Gemini Rotation:** Runs on **Google Gemini** (`gemini-3.5-flash`). Several API keys can be supplied; a key that hits a quota / rate limit is benched for a cooldown and the next one is used automatically (`GeminiKeyPool`). Chains are cached per key (`_CHAIN_CACHE`) and malformed tool-call replies fall back to SQL extraction.
* **Security & Guardrails:**
  * **AST Whitelist Validation:** Pandas filter expressions are parsed via Python's `ast` module (`is_safe_pandas_filter`) to permit only comparisons, boolean logic, `in` lists and basic arithmetic (no calls, attributes, dunder names or `**`).
  * **Read-Only Enforcement (defence in depth):** every SQL statement (agent or Playground) is validated as a single `SELECT`/`WITH` statement, *and* executed on a SQLite connection opened with `mode=ro`, so writes are refused by the engine itself. Results are capped at 200 rows.
  * **Path Sanitization:** Prevents directory traversal on uploaded or local files via `os.path.basename`.
  * **Chit-Chat Filtering:** Lightweight heuristic (`_is_chitchat`) intercepts greetings and conversational filler without wasting LLM API calls.
* **Interactive Streamlit Web UI & CLI:** Includes a custom dark-themed Streamlit dashboard with a live **ReAct Trace sidebar** (`Thought → Action → Observation`), interactive data tables, a Schema & Excel uploader tab, a raw SQL Playground, and a standalone CLI loop (`main.py`).

---

## 📂 Project Structure

```text
autonomous-db-agent/
├── agent/
│   ├── __init__.py                 # Exports core agent functions and Pydantic schemas
│   ├── api/
│   │   ├── __init__.py
│   │   └── llm_config.py           # Gemini init, multi-key rotation pool, quota detection
│   └── langchain_react/
│       ├── __init__.py
│       ├── prompt.py               # Pydantic schemas (XAI, SQL/Excel outputs) & PromptTemplates
│       └── react_agent.py          # Core execution engine, reflection loop, AST security, XAI tree
├── database/
│   ├── __init__.py
│   ├── company.db                  # SQLite database (auto-generated and seeded if missing)
│   ├── schema.sql                  # DDL schema for Departments, Employees, and Sales tables
│   └── db_manager.py               # Database seeding (via Faker), query runner, and schema reader
├── .gitignore                      # Ignores .env, venv/, __pycache__/, and database/company.db
├── requirements.txt                # Project Python dependencies
├── process.md                      # Environment setup notes and dependency overview
├── main.py                         # Interactive Command-Line Interface (CLI) entry point
├── app.py                          # Streamlit Web UI with live ReAct trace and 4 interactive tabs
├── tests/                          # pytest suite (mocked LLM) - run: pytest -q
├── live_attack.py                  # Live red-team script against real Gemini
├── .env.example                    # Template for API keys
├── test_api.py                     # Diagnostic script to verify every Gemini API key
└── test_db_agent.py                # Standalone test script using LangChain's SQLDatabase toolkit
```

---

## 🗃️ Database Schema (`database/schema.sql`)

When no database file is detected, `database/db_manager.py` automatically builds `company.db` and seeds it using `Faker`:

1. **`Departments`** (5 seeded departments: *Sales, Engineering, Marketing, Human Resources, Finance*):
   * `Dept_Id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   * `Dept_Name` (`TEXT NOT NULL`)
   * `Location` (`TEXT NOT NULL`)
2. **`Employees`** (40 randomly generated employee records with salaries between `$35,000` and `$150,000`):
   * `Emp_Id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   * `Emp_Name` (`TEXT NOT NULL`)
   * `Dept_Id` (`INTEGER NOT NULL`, Foreign Key → `Departments.Dept_Id`)
   * `Salary` (`REAL NOT NULL`)
3. **`Sales`** (40 randomly generated sales transactions between `$100` and `$20,000` over the past year):
   * `Sale_Id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   * `Amount` (`REAL NOT NULL`)
   * `Date` (`TEXT NOT NULL`, ISO format `YYYY-MM-DD`)
   * `Emp_Id` (`INTEGER NOT NULL`, Foreign Key → `Employees.Emp_Id`)

---

## ⚙️ Installation & Setup

### 1. Prerequisites
* **Python 3.10+** installed on your machine.
* One or more API keys for **Google Gemini** ([Google AI Studio](https://aistudio.google.com/)).

### 2. Clone the Repository & Create a Virtual Environment

```bash
git clone https://github.com/VeerVSR/autonomous-db-agent.git
cd autonomous-db-agent

# Create a virtual environment
python -m venv venv
```

Activate the virtual environment:
* **Windows (PowerShell):**
  ```powershell
  venv\Scripts\Activate.ps1
  ```
* **Windows (Command Prompt):**
  ```cmd
  venv\Scripts\activate.bat
  ```
* **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory of the project and add your API keys:

```env
# One key, or several comma-separated on ONE line (rotated on quota errors)
GEMINI_API_KEYS=key1,key2,key3
# Optional: seconds to bench an exhausted key (default 60)
# GEMINI_KEY_COOLDOWN_SECONDS=60
```
(A `.env.example` is included - copy it to `.env`. The legacy single `GEMINI_API_KEY` is still read.)

---

## 🚀 Usage

### 1. Verify API Connectivity (Optional)
Test that every Gemini key in your `.env` works:

```bash
python test_api.py
```

### 2. Launch the Streamlit Web UI (Recommended)
Start the interactive web interface:

```bash
streamlit run app.py
```

* **💬 Chat Tab:** Ask questions in natural language, use quick-prompt chips, inspect generated SQL/Pandas expressions, view results in interactive dataframes, and expand self-healing retry logs.
* **🗂️ Schema Tab:** Inspect the active SQLite DDL schema or upload an `.xlsx` / `.xls` spreadsheet to switch the agent's active data source on the fly.
* **🧪 Playground Tab:** Execute read-only `SELECT` queries directly against `company.db`, bypassing the LLM.
* **⚙️ Settings Tab:** Adjust the **Self-healing retries** slider (`0` to `5`), rebuild/re-seed the SQLite database with fresh sample data, or clear chat and trace history.

### 3. Run via Command-Line Interface (CLI)
For a lightweight terminal loop that outputs the executed expression, raw data, and the ASCII Explainable AI tree:

```bash
python main.py
```
*(Type `exit` at the prompt to quit.)*

### 4. Manually Seed / Reset the Database
Both `app.py` and `main.py` auto-generate `database/company.db` on first run if it does not exist. To manually rebuild and re-seed the database with fresh `Faker` data at any time:

```bash
python -m database.db_manager
```

### 5. Run the automated test suite

```bash
pip install -r requirements-dev.txt
pytest -q
```

### 6. Run the LangChain SQL Toolkit Test
To test the database connection against standard LangChain `create_sql_agent`:

```bash
python test_db_agent.py
```

---

## 🔍 Explainable AI (XAI) Telemetry Format

Every call to `run_agent()` validates its output against the `RunAgentResult` Pydantic contract and renders an XAI telemetry tree via `render_xai_tree()`:

```text
+-- [EXPLAINABLE AI TELEMETRY]
|   +-- Origin        : LOCAL_REPO
|   +-- Source        : SQL (company.db)
|   +-- Entity Target : SQLite Database Tables
|   +-- Confidence    : High
|   +-- Rationale     : Joined Departments, Employees, and Sales to aggregate total sales amount per department, ordered descending and limited to 5.
|   +-- Self-Healing Audit: 0 Retries (Success on attempt 1)
+-- Returned Records  : 5 rows
```

### Confidence Scoring Logic
* **`High`**: Query succeeded on the first attempt (`0` retries) and returned `1` or more rows.
* **`Medium`**: Query initially failed, recovered via the Self-Healing Reflection Loop (`1+` retries), and returned `1` or more rows.
* **`Low (Zero Rows Match)`**: Query executed without syntax errors, but matched `0` records.
* **`Failed`**: Query failed even after exhausting all configured reflection retries.

---

## 🛠️ Tech Stack

| Component | Technology |
| :--- | :--- |
| **Agent Orchestration** | `langchain`, `langchain-core`, `langchain-community` |
| **LLM Provider** | `langchain-google-genai` (`gemini-3.5-flash`) |
| **Structured Outputs** | `pydantic` (`BaseModel`, `Field`) |
| **Frontend UI** | `streamlit` |
| **Data Processing & DB** | `sqlite3`, `pandas`, `openpyxl`, `Faker` |
| **Environment Management** | `python-dotenv` |
