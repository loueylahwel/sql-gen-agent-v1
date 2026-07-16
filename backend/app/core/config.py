from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    # Comma-separated list of keys for round-robin rotation / rate-limit failover
    GROQ_API_KEYS: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    ROW_LIMIT: int = 500

    class Config:
        env_file = ".env"

settings = Settings()
