from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "personal-finance-manager"
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5000
    cors_origins: str = ""
    backend_host: str = "127.0.0.1"
    backend_port: int = 9999
    backend_reload: bool = True
    api_root_path: str = ""
    cookie_secure: bool = False
    secret_key: str = Field(min_length=12)
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str
    database_ssl_mode: str = "disable"
    max_upload_mb: int = 25
    upload_storage_dir: str = "backend/storage/imports"

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password)
        return (
            f"postgresql+psycopg://{user}:{password}@{self.database_host}:"
            f"{self.database_port}/{self.database_name}?sslmode={self.database_ssl_mode}"
        )

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_storage_dir)
        return path if path.is_absolute() else ROOT / path

    @property
    def allowed_origins(self) -> list[str]:
        configured = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
        defaults = [
            f"http://{self.frontend_host}:{self.frontend_port}",
            f"http://localhost:{self.frontend_port}",
            f"http://127.0.0.1:{self.frontend_port}",
        ]
        return list(dict.fromkeys(configured + defaults))


@lru_cache
def get_settings() -> Settings:
    return Settings()
