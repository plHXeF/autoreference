import pytest

from autoreference.config import Settings


def test_settings_do_not_require_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOREFERENCE_API_KEY", raising=False)
    settings = Settings.from_env()
    assert settings.openai_api_key is None
    assert settings.llm_enabled is False
    assert settings.effort_for("query") == "low"
    assert settings.effort_for("judge") == "high"


def test_explicit_max_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOREFERENCE_REASONING_EFFORT", "max")
    settings = Settings.from_env()
    assert settings.effort_for("query") == "max"
    assert settings.effort_for("judge") == "max"

