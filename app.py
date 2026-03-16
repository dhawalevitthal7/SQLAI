import os
import json
import base64
import glob
import tempfile
import hashlib
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
from sqlglot import exp, parse_one
from psycopg2 import sql

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CACHE_DB_URL = os.getenv("CACHE_DB_URL", "")
MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_API_KEY)

# --- Pydantic Models ---

class DBConnectionRequest(BaseModel):
    db_url: str = Field(..., description="The Target Database Connection String")

class UserRequest(BaseModel):
    db_url: str = Field(..., description="The Target Database Connection String")
    query: str = Field(..., description="Natural language question")
    safe_mode: bool = Field(True, description="True = SELECT only. False = Allows INSERT/UPDATE/DROP etc.")

class AnalysisResponse(BaseModel):
    sql_query: str
    message: Optional[str] = "Query executed successfully."
    data_preview: Optional[List[Dict[str, Any]]] = None
    graphs_base64: List[str] = []
    error: Optional[str] = None

class TableDetailsResponse(BaseModel):
    table_name: str
    row_count: int
    columns: List[str]
    first_10: List[Dict[str, Any]]
    last_10: List[Dict[str, Any]]

# --- Cache & Database Functions ---

def init_cache_db():
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_cache (
                db_hash TEXT PRIMARY KEY,
                schema_text TEXT,
                context_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Cache table ready.")
    except Exception as e:
        print(f"❌ Cache Init Error: {e}")

def get_cached_schema(db_hash: str):
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT schema_text, context_text FROM schema_cache WHERE db_hash = %s", (db_hash,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            return {"schema": result[0], "context": result[1]}
        return None
    except Exception as e:
        print(f"⚠️ Cache Read Error: {e}")
        return None

def save_cached_schema(db_hash: str, schema_text: str, context_text: str):
    try:
        conn = psycopg2.connect(CACHE_DB_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO schema_cache (db_hash, schema_text, context_text)
            VALUES (%s, %s, %s)
            ON CONFLICT (db_hash) 
            DO UPDATE SET 
                schema_text = EXCLUDED.schema_text,
                context_text = EXCLUDED.context_text,
                updated_at = CURRENT_TIMESTAMP;
        """, (db_hash, schema_text, context_text))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Cache Write Error: {e}")

# --- Helper Functions ---

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

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

def fetch_target_schema(db_url: str) -> str:
    """Returns a string representation of the schema for the AI."""
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")
        tables = [t[0] for t in cur.fetchall()]
        
        output = []
        for table in tables:
            output.append(f"\nTable: {table}")
            cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s", (table,))
            cols = [f"{c[0]} ({c[1]})" for c in cur.fetchall()]
            output.append(f"Columns: {', '.join(cols)}")
        cur.close()
        conn.close()
        return "\n".join(output)
    except Exception as e:
        print(f"❌ DB Schema Fetch Error: {e}")
        return ""

def fetch_unique_context(db_url: str, schema_str: str) -> str:
    if not schema_str: return ""
    prompt = f"Analyze schema. Find categorical columns. Return JSON list: [{{'table': 't', 'column': 'c'}}]\nSchema: {schema_str}"
    try:
        resp = gemini_call(prompt, "Extract context")
        cols = json.loads(resp)
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        lines = []
        for item in cols:
            try:
                cur.execute(f"SELECT DISTINCT {item['column']} FROM {item['table']} LIMIT 10")
                vals = [str(r[0]) for r in cur.fetchall() if r[0]]
                lines.append(f"{item['table']}.{item['column']}: {', '.join(vals)}")
            except: continue
        cur.close()
        conn.close()
        return "\n".join(lines)
    except: return ""

def validate_sql_safety(sql: str, safe_mode: bool) -> bool:
    if not sql: return False
    if not safe_mode: return True
    try:
        parsed = parse_one(sql)
        return isinstance(parsed, (exp.Select, exp.With))
    except:
        return False

# --- Main App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_cache_db()
    yield

app = FastAPI(title="SQL GenAI Agent", lifespan=lifespan)

# --- New Endpoints ---

@app.post("/schemas")
def get_all_schemas(req: DBConnectionRequest):
    """Returns a structured JSON list of all tables and their columns."""
    try:
        conn = psycopg2.connect(req.db_url)
        cur = conn.cursor()
        
        # Get all tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        tables = [t[0] for t in cur.fetchall()]
        
        schema_data = {}
        
        for table in tables:
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s AND table_schema = 'public';
            """, (table,))
            columns = [{"name": row[0], "type": row[1]} for row in cur.fetchall()]
            schema_data[table] = columns
            
        cur.close()
        conn.close()
        return {"tables": schema_data}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")

@app.post("/schemas/{table_name}", response_model=TableDetailsResponse)
def get_table_details(table_name: str, req: DBConnectionRequest):
    """Returns row count, first 10 rows, and last 10 rows."""
    try:
        conn = psycopg2.connect(req.db_url)
        cur = conn.cursor()
        
        # 1. Security Check: Verify table exists to prevent SQL Injection
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = %s
            );
        """, (table_name,))
        exists = cur.fetchone()[0]
        
        if not exists:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

        # 2. Get Columns
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public';
        """, (table_name,))
        columns = [col[0] for col in cur.fetchall()]

        # 3. Get Row Count
        # Use sql.Identifier for safe table name quoting
        count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
        cur.execute(count_query)
        row_count = cur.fetchone()[0]

        # 4. Get First 10
        first_query = sql.SQL("SELECT * FROM {} LIMIT 10").format(sql.Identifier(table_name))
        cur.execute(first_query)
        first_10 = [dict(zip(columns, row)) for row in cur.fetchall()]

        # 5. Get Last 10
        # If we don't know the Primary Key, we use OFFSET based on count
        last_10 = []
        if row_count > 0:
            offset = max(0, row_count - 10)
            last_query = sql.SQL("SELECT * FROM {} OFFSET %s LIMIT 10").format(sql.Identifier(table_name))
            cur.execute(last_query, (offset,))
            last_10 = [dict(zip(columns, row)) for row in cur.fetchall()]

        cur.close()
        conn.close()

        return TableDetailsResponse(
            table_name=table_name,
            row_count=row_count,
            columns=columns,
            first_10=first_10,
            last_10=last_10
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")


# --- Existing Endpoint ---

@app.post("/generate", response_model=AnalysisResponse)
def generate_response(req: UserRequest):
    
    # 1. Cache Logic
    db_hash = get_hash(req.db_url)
    cached = get_cached_schema(db_hash)
    
    if cached:
        print("✅ Using Cached Schema")
        schema_str, context_str = cached["schema"], cached["context"]
    else:
        print("⏳ Fetching New Schema...")
        schema_str = fetch_target_schema(req.db_url)
        if not schema_str:
            return AnalysisResponse(sql_query="", error="Could not fetch database schema. Check your DB URL and permissions.")
            
        context_str = fetch_unique_context(req.db_url, schema_str)
        save_cached_schema(db_hash, schema_str, context_str)

    # 2. Build Prompt
    mode_instructions = (
        "STRICTLY READ-ONLY. Output ONLY SELECT statements." 
        if req.safe_mode 
        else "UNRESTRICTED MODE. You may generate INSERT, UPDATE, DELETE, CREATE, DROP, or SELECT statements."
    )

    system_prompt = f"""
    You are a PostgreSQL Expert.
    Schema: {schema_str}
    Context: {context_str}
    
    MODE: {mode_instructions}
    
    Rules:
    - Return strictly SQL. No markdown.
    - If user asks for 'most sold', assume COUNT(*) or SUM(quantity) grouped by product.
    """
    
    # 3. Generate SQL
    sql_query = gemini_call(system_prompt, req.query)
    
    if not sql_query:
        return AnalysisResponse(
            sql_query="", 
            error="AI failed to generate SQL. Likely causes: 1. Invalid API Key 2. Ambiguous Query"
        )
    
    # 4. Validate Safety
    if not validate_sql_safety(sql_query, req.safe_mode):
        return AnalysisResponse(
            sql_query=sql_query, 
            error="Safe Mode Violation: Query contains prohibited keywords."
        )

    # 5. Execute SQL
    try:
        conn = psycopg2.connect(req.db_url)
        conn.autocommit = False 
        cur = conn.cursor()
        
        cur.execute(sql_query)
        
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            df = pd.DataFrame(data, columns=columns)
            conn.commit()
            cur.close()
            conn.close()
            
            if df.empty:
                return AnalysisResponse(sql_query=sql_query, message="Query executed but returned no data.")
                
            graphs = []
            with tempfile.TemporaryDirectory() as temp_dir:
                csv_path = os.path.join(temp_dir, "data.csv")
                df.to_csv(csv_path, index=False)
                
                viz_prompt = f"""
                Visualize this data.
                Context: "{req.query}"
                Input: r'{csv_path}'
                Output: Save to r'{temp_dir}' using plt.savefig(). NO plt.show().
                Data Sample: {df.head(5).to_json()}
                """
                py_script = gemini_call(viz_prompt, "Generate Viz Code")
                
                try:
                    exec_globals = {"pd": pd, "plt": plt, "sns": sns}
                    exec(py_script, exec_globals)
                    for img in glob.glob(os.path.join(temp_dir, "*.png")):
                        with open(img, "rb") as f:
                            graphs.append(base64.b64encode(f.read()).decode('utf-8'))
                except Exception as e:
                    print(f"Viz error: {e}")

            return AnalysisResponse(
                sql_query=sql_query,
                message="Data retrieved successfully.",
                data_preview=df.head(20).to_dict(orient='records'),
                graphs_base64=graphs
            )
        else:
            conn.commit()
            cur.close()
            conn.close()
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