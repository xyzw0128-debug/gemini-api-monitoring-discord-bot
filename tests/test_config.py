import os

import pytest

from config import load_config


def test_config_expands_environment_and_accepts_variable_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BOT", "bot-token")
    monkeypatch.setenv("KEY_ONE", "one")
    monkeypatch.setenv("KEY_TWO", "two")
    path = tmp_path / "config.yaml"
    path.write_text("""discord:
  bot_token: ${BOT}
  channel_id: '1'
security:
  admin_user_ids: [123]
api_keys:
  - id: first
    value: ${KEY_ONE}
  - id: second
    value: ${KEY_TWO}
models: [google/gemini-one, google/gemini-two, google/gemini-three]
""", encoding="utf-8")
    config = load_config(path)
    assert len(config.initial_keys) == 2
    assert len(config.initial_models) == 3
    assert config.initial_keys[1].value == "two"


def test_config_rejects_duplicate_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BOT", "bot-token")
    path = tmp_path / "config.yaml"
    path.write_text("""discord:
  bot_token: ${BOT}
  channel_id: '1'
security:
  admin_user_ids: [123]
models: [google/gemini-one, google/gemini-one]
""", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate models"):
        load_config(path)


def test_config_requires_an_administrator_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BOT", "bot-token")
    path = tmp_path / "config.yaml"
    path.write_text("""discord:
  bot_token: ${BOT}
  channel_id: '1'
""", encoding="utf-8")
    with pytest.raises(ValueError, match="admin_user_ids"):
        load_config(path)
