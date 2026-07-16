from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    ROW_LIMIT: int = 500

    class Config:
        env_file = ".env"

settings = Settings()
