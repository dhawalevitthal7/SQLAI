import hashlib

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def get_dialect_name(db_url: str) -> str:
    if "postgres" in db_url: return "postgres"
    if "mysql" in db_url: return "mysql"
    if "oracle" in db_url: return "oracle"
    return "sql"
