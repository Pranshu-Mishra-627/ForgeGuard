"""Configuration management for ForgeGuard Orchestration Backend."""
from functools import lru_cache
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    # Server configuration
    orchestration_host: str = "0.0.0.0"
    orchestration_port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"

    # Engine service connection
    engine_base_url: str = "http://localhost:8001"
    engine_timeout_seconds: float = 10.0
    engine_retry_attempts: int = 2

    # ML service connection (if separate)
    ml_base_url: str = "http://localhost:8002"
    ml_timeout_seconds: float = 10.0

    # CORS
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Simulation defaults
    default_simulation_speed: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            # Split by comma if passed as comma-separated string
            if v.startswith("[") and v.endswith("]"):
                # JSON-like string
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache()
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()
