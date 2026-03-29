from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "quant-platform-backend"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://quant:quant@postgres:5432/quant"
    redis_url: str = "redis://redis:6379/0"
    polygon_api_key: str = ""
    parquet_cache_path: str = "/app/data/parquet"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
