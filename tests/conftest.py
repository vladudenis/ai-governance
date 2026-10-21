"""Shared pytest fixtures."""

import pytest

from ai_governance.config import Settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove application settings from the process environment.

    This keeps tests independent of variables set on the developer machine.
    """
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
