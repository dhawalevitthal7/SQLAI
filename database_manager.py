import json
from sqlalchemy import create_engine, inspect, text
from fastapi import HTTPException
import pandas as pd
from typing import Dict, Any, List

class DatabaseManager:
    @staticmethod
    def get_engine(db_url: str):
        try:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://")
            return create_engine(db_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Database Connection Error: {str(e)}")

    @staticmethod
    def get_tables(db_url: str) -> List[str]:
        try:
            engine = DatabaseManager.get_engine(db_url)
            inspector = inspect(engine)
            return inspector.get_table_names()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")

    @staticmethod
    def fetch_universal_schema(db_url: str) -> str:
        try:
            engine = DatabaseManager.get_engine(db_url)
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

    @staticmethod
    def get_all_schemas(db_url: str) -> Dict[str, List[Dict[str, str]]]:
        try:
            engine = DatabaseManager.get_engine(db_url)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            schema_data = {}
            for table in tables:
                columns = inspector.get_columns(table)
                schema_data[table] = [{"name": c['name'], "type": str(c['type'])} for c in columns]
            return schema_data
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Database Error: {str(e)}")

    @staticmethod
    def fetch_unique_context(db_url: str, schema_str: str, ai_service) -> str:
        if not schema_str: return ""
        prompt = f"Analyze schema. Find categorical columns. Return JSON list: [{{'table': 't', 'column': 'c'}}]\nSchema: {schema_str}"
        try:
            resp = ai_service.gemini_call(prompt, "Extract context")
            cols = json.loads(resp)
            engine = DatabaseManager.get_engine(db_url)
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

    @staticmethod
    def get_table_details(db_url: str, table_name: str, dialect_name: str):
        try:
            engine = DatabaseManager.get_engine(db_url)
            inspector = inspect(engine)
            if not inspector.has_table(table_name):
                 raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
            
            columns_info = inspector.get_columns(table_name)
            col_names = [c['name'] for c in columns_info]
            
            with engine.connect() as conn:
                count_res = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = count_res.scalar()
                
                if dialect_name == 'oracle':
                    q_first = f"SELECT * FROM {table_name} OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
                    offset = max(0, row_count - 10)
                    q_last = f"SELECT * FROM {table_name} OFFSET {offset} ROWS FETCH NEXT 10 ROWS ONLY"
                elif dialect_name in ['mysql', 'postgres']:
                    q_first = f"SELECT * FROM {table_name} LIMIT 10"
                    offset = max(0, row_count - 10)
                    q_last = f"SELECT * FROM {table_name} LIMIT 10 OFFSET {offset}"
                else:
                    q_first = f"SELECT * FROM {table_name}"
                    q_last = f"SELECT * FROM {table_name}"

                df_first = pd.read_sql(text(q_first), conn)
                df_last = pd.read_sql(text(q_last), conn)

            if dialect_name not in ['oracle', 'mysql', 'postgres']:
                df_first = df_first.head(10)
                df_last = df_last.tail(10)

            first_10 = json.loads(df_first.to_json(orient='records', date_format='iso'))
            last_10 = json.loads(df_last.to_json(orient='records', date_format='iso'))

            return {
                "table_name": table_name,
                "row_count": row_count,
                "columns": col_names,
                "first_10": first_10,
                "last_10": last_10
            }
        except Exception as e:
            if isinstance(e, HTTPException): raise e
            raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")
