import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    CACHE_DB_URL: str = os.getenv("CACHE_DB_URL", "")
    MODEL_NAME: str = "gemini-2.5-flash"

    class Config:
        env_file = ".env"

settings = Settings()
