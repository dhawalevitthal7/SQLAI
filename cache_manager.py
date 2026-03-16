import psycopg2
from datetime import datetime

class CacheManager:
    def __init__(self, cache_db_url: str):
        self.cache_db_url = cache_db_url

    def init_cache_db(self):
        try:
            conn = psycopg2.connect(self.cache_db_url)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_cache (
                    db_hash TEXT PRIMARY KEY,
                    schema_text TEXT,
                    context_text TEXT,
                    dialect TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                ALTER TABLE schema_cache 
                ADD COLUMN IF NOT EXISTS dialect TEXT;
            """)
            conn.commit()
            cur.close()
            conn.close()
            print("✅ Cache table ready.")
        except Exception as e:
            print(f"❌ Cache Init Error: {e}")

    def get_cached_schema(self, db_hash: str):
        try:
            conn = psycopg2.connect(self.cache_db_url)
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

    def save_cached_schema(self, db_hash: str, schema_text: str, context_text: str, dialect: str):
        try:
            conn = psycopg2.connect(self.cache_db_url)
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
