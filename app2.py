import os
import json
import math
import base64
import tempfile
import io
import pandas as pd
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text

# Import refactored modules
from models import (
    DBConnectionRequest, UserRequest, AnalysisResponse, 
    TableDetailsResponse, DashboardResponse, DashboardChart,
    OptimizeRequest, OptimizeResponse, PaginationRequest, PaginationResponse
)
from database_manager import DatabaseManager
from cache_manager import CacheManager
from ai_service import AIService
from viz_service import VizService
from utils import get_hash, get_dialect_name

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CACHE_DB_URL = os.getenv("CACHE_DB_URL", "")
MODEL_NAME = "gemini-2.5-flash"

# --- Services ---
ai_service = AIService(api_key=GEMINI_API_KEY, model_name=MODEL_NAME)
cache_manager = CacheManager(cache_db_url=CACHE_DB_URL)
db_manager = DatabaseManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache_manager.init_cache_db()
    yield

app = FastAPI(title="Multi-DB SQL Agent", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.post("/schemas")
def get_all_schemas(req: DBConnectionRequest):
    return {"tables": db_manager.get_tables(req.db_url)}

@app.post("/schemas/{table_name}", response_model=TableDetailsResponse)
def get_table_details(table_name: str, req: DBConnectionRequest):
    dialect = get_dialect_name(req.db_url)
    details = db_manager.get_table_details(req.db_url, table_name, dialect)
    return TableDetailsResponse(**details)

@app.post("/schemas/{table_name}/data", response_model=PaginationResponse)
def get_table_data(table_name: str, req: PaginationRequest):
    """
    Fetches table data with server-side pagination.
    Handles dialect differences for LIMIT/OFFSET syntax.
    """
    try:
        # 1. Security: Validate table existence to prevent SQL Injection
        # Table names cannot be bound as parameters, so we must whitelist them.
        existing_tables = db_manager.get_tables(req.db_url)
        if table_name not in existing_tables:
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

        engine = db_manager.get_engine(req.db_url)
        dialect = get_dialect_name(req.db_url).lower()
        
        # 2. Get Total Row Count
        count_sql = f"SELECT COUNT(*) FROM {table_name}"
        
        with engine.connect() as conn:
            # Execute Count
            total_rows = conn.execute(text(count_sql)).scalar()
            
            # Calculate Pagination
            req.page = max(1, req.page) # Ensure page is at least 1
            offset = (req.page - 1) * req.limit
            total_pages = math.ceil(total_rows / req.limit) if total_rows > 0 else 1

            # 3. Construct Data Query based on Dialect
            # MSSQL uses OFFSET ... FETCH NEXT (and requires ORDER BY)
            # Oracle 12c+ uses OFFSET ... FETCH NEXT
            # MySQL, PostgreSQL, SQLite use LIMIT ... OFFSET
            
            if "mssql" in dialect or "sqlserver" in dialect:
                # MSSQL requires an ORDER BY clause for OFFSET to work. 
                # We use (SELECT NULL) as a dummy sort if no primary key is known.
                data_sql = f"""
                    SELECT * FROM {table_name} 
                    ORDER BY (SELECT NULL) 
                    OFFSET {offset} ROWS 
                    FETCH NEXT {req.limit} ROWS ONLY
                """
            elif "oracle" in dialect:
                data_sql = f"""
                    SELECT * FROM {table_name} 
                    OFFSET {offset} ROWS 
                    FETCH NEXT {req.limit} ROWS ONLY
                """
            else:
                # Standard syntax for Postgres, MySQL, SQLite
                data_sql = f"SELECT * FROM {table_name} LIMIT {req.limit} OFFSET {offset}"

            # 4. Fetch Data using Pandas
            df = pd.read_sql(text(data_sql), conn)
            
            # Format data to JSON (handle dates correctly)
            data_json = json.loads(df.to_json(orient='records', date_format='iso'))

            return PaginationResponse(
                data=data_json,
                total_rows=total_rows,
                page=req.page,
                total_pages=total_pages
            )

    except Exception as e:
        # Check if it's a specific HTTP exception (like table not found)
        if isinstance(e, HTTPException):
            raise e
        return PaginationResponse(
            data=[], total_rows=0, page=0, total_pages=0, 
            error=f"Error fetching data: {str(e)}"
        )

@app.post("/generate", response_model=AnalysisResponse)
def generate_response(req: UserRequest):
    dialect = get_dialect_name(req.db_url)
    db_hash = get_hash(req.db_url)
    cached = cache_manager.get_cached_schema(db_hash)
    
    if cached:
        schema_str, context_str = cached["schema"], cached["context"]
    else:
        schema_str = db_manager.fetch_universal_schema(req.db_url)
        if not schema_str:
            return AnalysisResponse(sql_query="", error="Could not fetch database schema.")
        context_str = db_manager.fetch_unique_context(req.db_url, schema_str, ai_service)
        cache_manager.save_cached_schema(db_hash, schema_str, context_str, dialect)

    mode_instructions = "STRICTLY READ-ONLY. SELECT only." if req.safe_mode else "UNRESTRICTED MODE."
    system_prompt = f"""
    You are a {dialect.upper()} SQL Expert.
    Schema: {schema_str}
    Context: {context_str}
    MODE: {mode_instructions}
    Rules: 
    - Return strictly raw SQL. No markdown.
    - Handle date comparisons using dialect-specific functions.
    """
    
    sql_query = ai_service.gemini_call(system_prompt, req.query)
    if not sql_query:
        return AnalysisResponse(sql_query="", error="AI failed to generate SQL.")
    
    attempts = 0
    max_retries = 1
    last_error = None
    
    while attempts <= max_retries:
        if not ai_service.validate_sql_safety(sql_query, req.safe_mode):
            return AnalysisResponse(sql_query=sql_query, error="Safe Mode Violation.")

        try:
            engine = db_manager.get_engine(req.db_url)
            is_select = any(sql_query.strip().lower().startswith(p) for p in ["select", "with"])
            
            if is_select:
                with engine.connect() as conn:
                    df = pd.read_sql(text(sql_query), conn)
                
                if df.empty:
                    return AnalysisResponse(sql_query=sql_query, message="Query executed but returned no data.")
                
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                csv_base64 = base64.b64encode(csv_buffer.getvalue().encode('utf-8')).decode('utf-8')
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    graphs = VizService.generate_visualizations(df, req.query, ai_service, temp_dir)

                data_preview = json.loads(df.head(20).to_json(orient='records', date_format='iso'))

                return AnalysisResponse(
                    sql_query=sql_query,
                    message="Data retrieved successfully." if attempts == 0 else f"Data retrieved successfully after auto-correction.",
                    data_preview=data_preview,
                    graphs_base64=graphs,
                    csv_base64=csv_base64
                )
            else:
                with engine.begin() as conn:
                    conn.execute(text(sql_query))
                return AnalysisResponse(
                    sql_query=sql_query, 
                    message="Command executed successfully. Database updated." if attempts == 0 else f"Command executed successfully after auto-correction.", 
                    data_preview=None, 
                    graphs_base64=[]
                )
        except Exception as e:
            last_error = str(e)
            attempts += 1
            if attempts <= max_retries:
                print(f"🔄 Retrying SQL correction... Attempt {attempts}. Error: {last_error}")
                # Use cached schema_str if available, else fetch it
                sql_query = ai_service.fix_sql(sql_query, last_error, schema_str, dialect)
                if not sql_query:
                    break
            else:
                break
    
    return AnalysisResponse(sql_query=sql_query, error=f"SQL Execution Error: {last_error}")

@app.post("/gen-dashboard", response_model=DashboardResponse)
def generate_dashboard(req: DBConnectionRequest):
    dialect = get_dialect_name(req.db_url)
    db_hash = get_hash(req.db_url)
    cached = cache_manager.get_cached_schema(db_hash)
    
    if cached:
        schema_str, context_str = cached["schema"], cached["context"]
    else:
        schema_str = db_manager.fetch_universal_schema(req.db_url)
        if not schema_str:
            return DashboardResponse(charts=[], error="Could not fetch database schema.")
        context_str = db_manager.fetch_unique_context(req.db_url, schema_str, ai_service)
        cache_manager.save_cached_schema(db_hash, schema_str, context_str, dialect)

    strategy_prompt = f"""
    You are a Senior Data Scientist using {dialect.upper()} SQL.
    Your goal is to create a professional dashboard with 5 distinct, high-value insights.
    Schema: {schema_str}
    Context: {context_str}
    Task:
    Generate a JSON list of 5 objects. Each object must have:
    1. 'title': A business title for the chart.
    2. 'description': A 1-sentence insight explaining what this shows.
    3. 'sql_query': The raw SQL query to fetch the data (must be SELECT).
    Format strictly as JSON.
    """
    
    try:
        raw_plan = ai_service.gemini_call(strategy_prompt, "Generate Dashboard Plan")
        dashboard_plan = json.loads(raw_plan)
        if not isinstance(dashboard_plan, list):
            raise ValueError("AI returned invalid JSON structure")
    except Exception as e:
        return DashboardResponse(charts=[], error=f"Failed to generate dashboard plan: {e}")

    generated_charts = []
    engine = db_manager.get_engine(req.db_url)

    for item in dashboard_plan[:5]:
        try:
            sql = item.get("sql_query")
            title = item.get("title")
            desc = item.get("description")
            
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            
            if df.empty: continue 

            with tempfile.TemporaryDirectory() as temp_dir:
                graphs = VizService.generate_visualizations(df, desc, ai_service, temp_dir)
                if graphs:
                    generated_charts.append(DashboardChart(
                        title=title,
                        description=desc,
                        graph_base64=graphs[0]
                    ))
        except Exception as err:
            print(f"Chart generation failed for {item.get('title', 'Unknown')}: {err}")
            continue

    return DashboardResponse(charts=generated_charts)

@app.post("/optimize", response_model=OptimizeResponse)
def optimize_sql(req: OptimizeRequest):
    dialect = get_dialect_name(req.db_url)
    db_hash = get_hash(req.db_url)
    cached = cache_manager.get_cached_schema(db_hash)
    
    if cached:
        schema_str = cached["schema"]
    else:
        schema_str = db_manager.fetch_universal_schema(req.db_url)
        if not schema_str:
            raise HTTPException(status_code=400, detail="Could not fetch database schema.")
        cache_manager.save_cached_schema(db_hash, schema_str, "", dialect)

    system_prompt = f"""
    You are a Senior {dialect.upper()} DBA and SQL Performance Expert.
    Database Schema: 
    {schema_str}

    Your Task:
    Analyze the user's input SQL query.
    1. Check for syntax errors.
    2. Check for logical errors.
    3. Optimize for performance.
    4. Ensure it is valid {dialect.upper()} SQL.

    Output strictly valid JSON:
    {{
        "optimized_sql": "THE_REFINED_SQL_QUERY",
        "explanation": "Brief markdown explanation.",
        "difference_score": 0
    }}
    """
    user_content = f"Input SQL: {req.query}"

    try:
        response_text = ai_service.gemini_call(system_prompt, user_content)
        result = json.loads(response_text)
        
        return OptimizeResponse(
            original_query=req.query,
            optimized_query=result.get("optimized_sql", req.query),
            explanation=result.get("explanation", "Analysis complete."),
            difference_score=result.get("difference_score", 0)
        )
    except json.JSONDecodeError:
        return OptimizeResponse(
            original_query=req.query,
            optimized_query=req.query,
            explanation="AI Analysis failed to format response correctly. Returning original.",
            difference_score=0
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)