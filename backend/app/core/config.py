from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CLICKHOUSE_HOST: str = "j208km7gg3.germanywestcentral.azure.clickhouse.cloud"
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = "erynQOtW_Hnr8"
    CLICKHOUSE_SECURE: bool = True
    CLICKHOUSE_DATABASE: str = "default"

    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "gpt-oss:120b-cloud"

    ROW_LIMIT: int = 500

    class Config:
        env_file = ".env"

settings = Settings()