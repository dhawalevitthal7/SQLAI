# SQLAI — Multi-Database AI Agent

> **Natural language to SQL. Instant visualizations. AI-powered dashboards. Zero SQL expertise required.**

SQLAI is an intelligent, multi-database AI agent built with FastAPI and Google Gemini 2.5 Flash. Connect any database, ask questions in plain English, and get instant SQL execution, auto-generated charts, paginated schema exploration, and one-click dashboards — all from a single dark-mode web interface.

---

## Features

| Feature | Description |
|---------|-------------|
| **NLQ  SQL** | Describe what you want in plain English; Gemini generates and executes the correct SQL |
| **Multi-DB Support** | PostgreSQL, MySQL, MariaDB, Oracle, MS SQL Server, SQLite — one API for all |
| **Auto-Correct** | On SQL execution failure, the AI automatically fixes and retries the query |
| **Schema Explorer** | Browse tables, column types, row counts, first/last 10 rows with server-side pagination |
| **AI Dashboard** | Auto-generates 5 business-insight charts from schema analysis in one click |
| **SQL Optimizer** | Paste any SQL — get syntax fixes, logic improvements, and a performance-optimized version |
| **Visualizations** | AI writes and executes matplotlib/seaborn code to produce charts for every query result |
| **CSV Export** | Every query result is instantly downloadable as a CSV |
| **Schema Cache** | Database schemas are MD5-hashed and cached in NeonDB to avoid redundant introspection |
| **Safe Mode** | Toggle to restrict queries to SELECT-only, preventing destructive operations |
| **Dark UI** | Responsive single-page frontend with sidebar navigation, served directly by FastAPI |

---

## Architecture

```
Browser (SPA Frontend)
        |  HTTP
        v
+--------------------------------------------------+
|  FastAPI  (app2.py)                              |
|                                                  |
|  GET  /               -> serve frontend          |
|  POST /schemas        -> list tables             |
|  POST /schemas/{t}    -> table details           |
|  POST /schemas/{t}/data -> paginated data        |
|  POST /generate       -> NLQ -> SQL+result+viz   |
|  POST /gen-dashboard  -> 5-chart auto dashboard  |
|  POST /optimize       -> SQL review & optimize   |
+------+-------------------------------------------+
       |
  +----+------------------------------------------+
  |              Service Layer                    |
  |                                               |
  |  AIService        (ai_service.py)             |
  |   +- Gemini 2.5 Flash API calls               |
  |   +- SQL safety validation                    |
  |   +- Auto SQL-fix on error                    |
  |                                               |
  |  DatabaseManager  (database_manager.py)       |
  |   +- SQLAlchemy universal connector           |
  |   +- Schema introspection (reflect)           |
  |   +- Dialect-aware query execution            |
  |                                               |
  |  VizService       (viz_service.py)            |
  |   +- AI generates matplotlib/seaborn code     |
  |   +- Safe exec sandbox                        |
  |   +- Returns base64-encoded charts            |
  |                                               |
  |  CacheManager     (cache_manager.py)          |
  |   +- NeonDB PostgreSQL schema cache           |
  |   +- MD5 hash keying per DB URL               |
  +-----------------------------------------------+
       |
  Target Databases: PostgreSQL  MySQL  Oracle  MSSQL  SQLite
```

---

## Project Structure

```
SQLAI/
 app2.py              # Main FastAPI application (production entry point)
 app.py               # Monolithic prototype (reference only)
 app1.py              # Intermediate refactor (reference only)
 models.py            # Pydantic request/response models
 database_manager.py  # DB connection, schema discovery, query execution
 ai_service.py        # Google Gemini API calls, SQL safety, auto-fix
 cache_manager.py     # NeonDB schema caching layer
 viz_service.py       # AI-generated chart execution engine
 utils.py             # Helpers: URL hashing, dialect detection
 config.py            # Pydantic Settings (reads from .env)
 test_db_connection.py# DB connectivity sanity check
 requirements.txt     # Pinned Python dependencies
 .env.example         # Environment variable template
 frontend/
    index.html       # Single-page app with sidebar navigation
    styles.css       # Dark-mode responsive stylesheet
    app.js           # Frontend logic (fetch, rendering, state)
 README.md
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.129, Python 3.11+ |
| AI | Google Gemini 2.5 Flash (`google-genai`) |
| Databases | PostgreSQL, MySQL, Oracle, MSSQL, SQLite via SQLAlchemy 2.0 |
| SQL Validation | SQLGlot 28 |
| Visualization | Matplotlib 3.10, Seaborn 0.13, Pandas 3.0 |
| Schema Cache | NeonDB (PostgreSQL serverless) |
| DB Drivers | `psycopg2-binary`, `PyMySQL`, `oracledb` |
| Frontend | Vanilla HTML5 / CSS3 / JS (dark-mode SPA) |
| Server | Uvicorn |

---

## API Reference

### `POST /schemas`
List all table names in the connected database.
```json
Request:  { "db_url": "postgresql://user:pass@host/db" }
Response: { "tables": ["orders", "customers", "products"] }
```

### `POST /schemas/{table_name}`
Get column definitions, row count, first/last 10 rows.
```json
Request:  { "db_url": "..." }
Response: { "table_name": "orders", "row_count": 50000, "columns": [...], "first_10": [...], "last_10": [...] }
```

### `POST /schemas/{table_name}/data`
Paginated table data with dialect-aware SQL (`LIMIT/OFFSET`, `FETCH NEXT`, etc.).
```json
Request:  { "db_url": "...", "page": 1, "limit": 100 }
Response: { "data": [...], "total_rows": 50000, "page": 1, "total_pages": 500 }
```

### `POST /generate`
Core NLQ -> SQL -> execute -> visualize endpoint.
```json
Request:
{
  "db_url": "postgresql://...",
  "query": "Show monthly revenue for 2024 with a trend line",
  "safe_mode": true
}
Response:
{
  "sql_query": "SELECT DATE_TRUNC('month', ...) ...",
  "message": "Data retrieved successfully.",
  "data_preview": [...],
  "graphs_base64": ["iVBORw0KGgo..."],
  "csv_base64": "b3JkZXJfaWQs..."
}
```

### `POST /gen-dashboard`
Auto-generates 5 business-insight charts by analyzing schema + data.
```json
Request:  { "db_url": "..." }
Response: { "charts": [{ "title": "...", "description": "...", "graph_base64": "..." }, ...] }
```

### `POST /optimize`
Reviews SQL for syntax errors, logical issues, and performance improvements.
```json
Request:  { "db_url": "...", "query": "SELECT * FROM orders WHERE ..." }
Response: { "original_query": "...", "optimized_query": "...", "explanation": "...", "difference_score": 42 }
```

---

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/SQLAI.git
cd SQLAI
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
```
Edit `.env`:
```env
GEMINI_API_KEY=your_google_gemini_api_key_here
CACHE_DB_URL=postgresql://user:pass@host/db
```
Get your Gemini key at https://aistudio.google.com/app/apikey
Get a free NeonDB at https://neon.tech (or use any PostgreSQL instance for caching).

### 5. Run the server
```bash
uvicorn app2:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

---

## Supported Database URL Formats

```bash
# PostgreSQL
postgresql://user:password@host:5432/dbname

# MySQL / MariaDB
mysql+pymysql://user:password@host:3306/dbname

# SQLite
sqlite:///path/to/database.db

# Oracle
oracle+oracledb://user:password@host:1521/service_name

# MS SQL Server
mssql+pyodbc://user:password@host/dbname?driver=ODBC+Driver+17+for+SQL+Server
```

---

## How It Works

1. **Connect** — paste your database connection string into the web UI.
2. **Auto-cache** — the backend introspects your schema, extracts unique categorical context, and caches both to NeonDB (keyed by MD5 hash of the URL). Subsequent requests skip schema fetching entirely.
3. **Query** — type a question like "what were the top 5 products by revenue last quarter?"
4. **Generate** — AIService.gemini_call() sends the schema + your question to Gemini 2.5 Flash, receiving raw SQL in return.
5. **Validate** — validate_sql_safety() checks safe mode; if violated, returns an error before touching the DB.
6. **Execute** — SQLAlchemy runs the query. If it fails, fix_sql() asks Gemini to auto-correct the SQL (1 retry).
7. **Visualize** — VizService asks Gemini to write matplotlib/seaborn code specific to the returned DataFrame, then exec()s it in a sandboxed environment, captures PNG output as base64.
8. **Display** — charts + data table + CSV download button appear in the browser instantly.

---

## Key Design Decisions

- **Modular service classes** (AIService, DatabaseManager, VizService, CacheManager) — each independently testable and replaceable.
- **Schema caching** — database introspection is expensive; MD5-keyed caching in NeonDB makes repeated queries near-instant.
- **Auto SQL-fix with 1 retry** — rather than surfacing raw DB errors to users, the agent attempts one self-correction before giving up.
- **matplotlib.use('Agg')** — non-interactive backend set globally and defensively per-thread to prevent GUI crashes on headless servers.
- **Table name whitelisting** in paginated data endpoint — prevents SQL injection since table names cannot be parameterized in SQLAlchemy text().
- **Dialect-aware pagination** — LIMIT/OFFSET for Postgres/MySQL/SQLite, OFFSET FETCH NEXT for Oracle/MSSQL.

---

## Roadmap

- [ ] MySQL, Oracle, MSSQL dialect-specific SQL validation via SQLGlot
- [ ] Auth / API key middleware for multi-user deployments
- [ ] Query history sidebar
- [ ] Export dashboard as PDF report
- [ ] Streaming SQL generation (Server-Sent Events)
- [ ] Docker + docker-compose deployment

---

## Author

**Vitthal Dhawale**
B.Tech — AI & ML, RCOEM Nagpur
LinkedIn: https://linkedin.com/in/vitthaldhawale
GitHub: https://github.com/vitthaldhawale

---

## License

MIT — free to use, modify, and distribute.
