import json
from google import genai
from google.genai import types

class AIService:
    def __init__(self, api_key: str, model_name: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def gemini_call(self, system_instruction: str, user_content: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
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

    def validate_sql_safety(self, sql_query: str, safe_mode: bool) -> bool:
        if not sql_query: return False
        if not safe_mode: return True
        forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "grant", "revoke"]
        return not any(word in sql_query.lower() for word in forbidden)

    def fix_sql(self, original_sql: str, error_message: str, schema_str: str, dialect: str) -> str:
        system_instruction = f"You are a {dialect.upper()} SQL Expert. Fix the provided SQL based on the error message."
        user_content = f"Schema: {schema_str}\nOriginal SQL: {original_sql}\nError: {error_message}\nProvide ONLY the corrected raw SQL. No markdown."
        return self.gemini_call(system_instruction, user_content)
