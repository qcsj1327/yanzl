from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://futures:futures@localhost:5432/futures_mvp"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
