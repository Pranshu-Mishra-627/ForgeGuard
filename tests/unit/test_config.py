"""Unit tests for configuration loading and validation."""
import pytest
from app.config import Settings


def test_config_defaults():
    settings = Settings()
    assert settings.orchestration_host == "0.0.0.0"
    assert settings.orchestration_port == 8000
    assert settings.engine_timeout_seconds == 10.0
    assert "http://localhost:3000" in settings.cors_origins


def test_cors_origins_parsing():
    # Comma-separated string
    s1 = Settings(cors_origins="http://example.com, http://app.local")
    assert s1.cors_origins == ["http://example.com", "http://app.local"]

    # List of strings
    s2 = Settings(cors_origins=["http://alpha.com", "http://beta.com"])
    assert s2.cors_origins == ["http://alpha.com", "http://beta.com"]


def test_engine_url_formatting():
    s = Settings(engine_base_url="http://custom-engine:9000/")
    assert s.engine_base_url.rstrip("/") == "http://custom-engine:9000"
