import os
import json
import base64
import glob
import tempfile
import hashlib
import io
import pandas as pd
import psycopg2
import matplotlib

# Set backend to Agg to prevent GUI errors on servers
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from sqlalchemy import create_engine, inspect, text

# --- Configuration ---
# NOTE: It is recommended to use environment variables for keys in production.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyD9qRPGKMm9orOf54ObME4UakrG_dpA0oc")
CACHE_DB_URL = "postgresql://neondb_owner:npg_gYuacr4bXhU2@ep-spring-dawn-a1hl1f2r-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_API_KEY)

# --- Pydantic Models ---

class DBConnectionRequest(BaseModel):
    db_url: str = Field(..., description="Connection String")

class UserRequest(BaseModel):
    db_url: str = Field(..., description="Connection String")
    query: str = Field(..., description="Natural language question")
    safe_mode: bool = Field(True, description="True = SELECT only.")

class AnalysisResponse(BaseModel):
    sql_query: str
    message: Optional[str] = "Query executed successfully."
    data_preview: Optional[List[Dict[str, Any]]] = None
    graphs_base64: List[str] = []
    csv_base64: Optional[str] = None
    error: Optional[str] = None

class TableDetailsResponse(BaseModel):
    table_name: str
    row_count: int
    columns: List[str]
    first_10: List[Dict[str, Any]]
    last_10: List[Dict[str, Any]]

# --- Cache Functions (Internal Postgres) ---

def init_cache_db():
    """
    Initializes the cache table and performs auto-migration 
    to fix missing columns (like 'dialect') in existing tables.
    """
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        
        # 1. Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_cache (
                db_hash TEXT PRIMARY KEY,
                schema_text TEXT,
                context_text TEXT,
                dialect TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. AUTO-MIGRATION: Fix for "column dialect does not exist"
        # If the table existed from a previous run without 'dialect', this adds it.
        cur.execute("""
            ALTER TABLE schema_cache 
            ADD COLUMN IF NOT EXISTS dialect TEXT;
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Cache table ready (Schema Verified).")
    except Exception as e:
        print(f"❌ Cache Init Error: {e}")

def get_cached_schema(db_hash: str):
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT schema_text, context_text, dialect FROM schema_cache WHERE db_hash = %s", (db_hash,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            return {"schema": result[0], "context": result[1], "dialect": result[2]}
        return None
    except Exception:
        return None

def save_cached_schema(db_hash: str, schema_text: str, context_text: str, dialect: str):
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO schema_cache (db_hash, schema_text, context_text, dialect)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (db_hash) 
            DO UPDATE SET 
                schema_text = EXCLUDED.schema_text,
                context_text = EXCLUDED.context_text,
                dialect = EXCLUDED.dialect,
                updated_at = CURRENT_TIMESTAMP;
        """, (db_hash, schema_text, context_text, dialect))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Cache Write Error: {e}")

# --- Universal Database Helpers ---

def get_dialect_name(db_url: str) -> str:
    if "postgres" in db_url: return "postgres"
    if "mysql" in db_url: return "mysql"
    if "oracle" in db_url: return "oracle"
    return "sql"

def get_engine(db_url: str):
    try:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://")
        return create_engine(db_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database Connection Error: {str(e)}")

def fetch_universal_schema(db_url: str) -> str:
    try:
        engine = get_engine(db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        output = []
        for table in tables:
            output.append(f"\nTable: {table}")
            columns = inspector.get_columns(table)
            col_strs = [f"{c['name']} ({c['type']})" for c in columns]
            output.append(f"Columns: {', '.join(col_strs)}")
        return "\n".join(output)
    except Exception as e:
        print(f"❌ Schema Fetch Error: {e}")
        return ""

def fetch_unique_context(db_url: str, schema_str: str) -> str:
    if not schema_str: return ""
    prompt = f"Analyze schema. Find categorical columns. Return JSON list: [{{'table': 't', 'column': 'c'}}]\nSchema: {schema_str}"
    try:
        resp = gemini_call(prompt, "Extract context")
        cols = json.loads(resp)
        engine = get_engine(db_url)
        lines = []
        with engine.connect() as conn:
            for item in cols:
                try:
                    query = text(f"SELECT DISTINCT {item['column']} FROM {item['table']}")
                    result = conn.execute(query).fetchall()
                    vals = [str(row[0]) for row in result[:10] if row[0]]
                    lines.append(f"{item['table']}.{item['column']}: {', '.join(vals)}")
                except: continue
        return "\n".join(lines)
    except: return ""

def gemini_call(system_instruction: str, user_content: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
            contents=user_content
        )
        text = response.text
        if text.startswith("```"):
            text = text.replace("```sql", "").replace("```python", "").replace("```json", "").replace("```", "")
        return text.strip()
    except Exception as e:
        print(f"❌ Gemini API Error: {str(e)}")
        return ""

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def validate_sql_safety(sql_query: str, safe_mode: bool) -> bool:
    if not sql_query: return False
    if not safe_mode: return True
    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "grant", "revoke"]
    return not any(word in sql_query.lower() for word in forbidden)

# --- Main App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_cache_db()
    yield

app = FastAPI(title="Multi-DB SQL Agent", lifespan=lifespan)

@app.post("/schemas")
def get_all_schemas(req: DBConnectionRequest):
    try:
        engine = get_engine(req.db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        schema_data = {}
        for table in tables:
            columns = inspector.get_columns(table)
            schema_data[table] = [{"name": c['name'], "type": str(c['type'])} for c in columns]
        return {"tables": schema_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")

@app.post("/schemas/{table_name}", response_model=TableDetailsResponse)
def get_table_details(table_name: str, req: DBConnectionRequest):
    try:
        engine = get_engine(req.db_url)
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
             raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
        
        columns_info = inspector.get_columns(table_name)
        col_names = [c['name'] for c in columns_info]
        
        with engine.connect() as conn:
            # 1. Count
            count_res = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = count_res.scalar()

            # 2. Logic for First/Last 10 (Dialect Specific)
            dialect = get_dialect_name(req.db_url)
            
            if dialect == 'oracle':
                q_first = f"SELECT * FROM {table_name} OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
                offset = max(0, row_count - 10)
                q_last = f"SELECT * FROM {table_name} OFFSET {offset} ROWS FETCH NEXT 10 ROWS ONLY"
            elif dialect == 'mysql' or dialect == 'postgres':
                q_first = f"SELECT * FROM {table_name} LIMIT 10"
                offset = max(0, row_count - 10)
                q_last = f"SELECT * FROM {table_name} LIMIT 10 OFFSET {offset}"
            else:
                q_first = f"SELECT * FROM {table_name}"
                q_last = f"SELECT * FROM {table_name}"

            # 3. Fetch Data safely using text()
            df_first = pd.read_sql(text(q_first), conn)
            df_last = pd.read_sql(text(q_last), conn)

        # Fallback python slicing if dialect didn't support LIMIT/OFFSET in SQL
        if dialect not in ['oracle', 'mysql', 'postgres']:
            df_first = df_first.head(10)
            df_last = df_last.tail(10)

        first_10 = json.loads(df_first.to_json(orient='records', date_format='iso'))
        last_10 = json.loads(df_last.to_json(orient='records', date_format='iso'))

        return TableDetailsResponse(
            table_name=table_name,
            row_count=row_count,
            columns=col_names,
            first_10=first_10,
            last_10=last_10
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

@app.post("/generate", response_model=AnalysisResponse)
def generate_response(req: UserRequest):
    # 1. Determine Dialect & Cache
    dialect = get_dialect_name(req.db_url)
    db_hash = get_hash(req.db_url)
    cached = get_cached_schema(db_hash)
    
    if cached:
        print("✅ Using Cached Schema")
        schema_str, context_str = cached["schema"], cached["context"]
    else:
        print("⏳ Fetching New Schema...")
        schema_str = fetch_universal_schema(req.db_url)
        if not schema_str:
            return AnalysisResponse(sql_query="", error="Could not fetch database schema.")
        context_str = fetch_unique_context(req.db_url, schema_str)
        save_cached_schema(db_hash, schema_str, context_str, dialect)

    # 2. Build Prompt
    mode_instructions = "STRICTLY READ-ONLY. SELECT only." if req.safe_mode else "UNRESTRICTED MODE."
    dialect_instruction = f"You are a {dialect.upper()} SQL Expert."
    
    system_prompt = f"""
    {dialect_instruction}
    Schema: {schema_str}
    Context: {context_str}
    MODE: {mode_instructions}
    Rules: 
    - Return strictly raw SQL. No markdown.
    - Handle date comparisons using dialect-specific functions.
    """
    
    # 3. Generate SQL
    sql_query = gemini_call(system_prompt, req.query)
    if not sql_query:
        return AnalysisResponse(sql_query="", error="AI failed to generate SQL.")
    
    # 4. Validate Safety
    if not validate_sql_safety(sql_query, req.safe_mode):
        return AnalysisResponse(sql_query=sql_query, error="Safe Mode Violation.")

    # 5. Execute SQL
    try:
        engine = get_engine(req.db_url)
        is_select = sql_query.strip().lower().startswith("select") or sql_query.strip().lower().startswith("with")
        
        if is_select:
            with engine.connect() as conn:
                df = pd.read_sql(text(sql_query), conn)
            
            if df.empty:
                return AnalysisResponse(sql_query=sql_query, message="Query executed but returned no data.")
            
            # CSV
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_base64 = base64.b64encode(csv_buffer.getvalue().encode('utf-8')).decode('utf-8')
            
            # Graphs
            graphs = []
            with tempfile.TemporaryDirectory() as temp_dir:
                csv_path = os.path.join(temp_dir, "data.csv")
                df.to_csv(csv_path, index=False)
                
                viz_prompt = f"Visualize this. Context: {req.query}. Input: '{csv_path}'. Output: Save to '{temp_dir}' using plt.savefig(). NO plt.show(). Sample: {df.head(5).to_json()}"
                py_script = gemini_call(viz_prompt, "Generate Viz Code")
                try:
                    exec_globals = {"pd": pd, "plt": plt, "sns": sns}
                    exec(py_script, exec_globals)
                    for img in glob.glob(os.path.join(temp_dir, "*.png")):
                        with open(img, "rb") as f:
                            graphs.append(base64.b64encode(f.read()).decode('utf-8'))
                except Exception as e:
                    print(f"Viz error: {e}")

            data_preview = json.loads(df.head(20).to_json(orient='records', date_format='iso'))

            return AnalysisResponse(
                sql_query=sql_query,
                message="Data retrieved successfully.",
                data_preview=data_preview,
                graphs_base64=graphs,
                csv_base64=csv_base64
            )
        else:
            # Modification Query
            with engine.begin() as conn:
                conn.execute(text(sql_query))
            
            return AnalysisResponse(
                sql_query=sql_query, 
                message="Command executed successfully. Database updated.", 
                data_preview=None, 
                graphs_base64=[]
            )
            
    except Exception as e:
        return AnalysisResponse(sql_query=sql_query, error=f"SQL Execution Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)