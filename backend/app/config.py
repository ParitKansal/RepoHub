from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str  # required — app will refuse to start if not set
    database_url: str = "sqlite:///./gitclone.db"
    repos_dir: str = "repos"
    templates_dir: str = "frontend/templates"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    cors_origins: List[str] = []
    sentry_dsn: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
