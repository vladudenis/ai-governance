"""Checks for environment-based settings."""

import pytest
from pydantic import ValidationError

from ai_governance.config import Settings, get_settings


def test_defaults_do_not_require_an_llm_key(clean_env: None) -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.llm_enabled is False
    assert settings.llm_api_key is None
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.data_dir == "data"


def test_environment_overrides_defaults(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://ai_governance:change-me@localhost:5432/ai_governance_test",
    )
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("DATA_DIR", "data/test")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_url.endswith("/ai_governance_test")
    assert settings.llm_enabled is True
    assert settings.data_dir == "data/test"


def test_unknown_environment_name_is_rejected(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_api_key_is_masked(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test-secret")

    settings = Settings(_env_file=None)

    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test-secret"
    assert "sk-test-secret" not in repr(settings)


def test_get_settings_caches_the_first_result(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    first = get_settings()
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    second = get_settings()

    assert first is second
    assert second.log_level == "DEBUG"
    get_settings.cache_clear()
