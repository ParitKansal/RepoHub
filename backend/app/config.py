from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./gitclone.db"
    repos_dir: str = "repos"
    templates_dir: str = "frontend/templates"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    class Config:
        env_file = ".env"


settings = Settings()
