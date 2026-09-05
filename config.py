"""Configuration loading and ${ENV_VAR} substitution."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from models import ApiKey

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class DiscordConfig:
    bot_token: str
    channel_id: int


@dataclass(frozen=True)
class SecurityConfig:
    admin_user_ids: frozenset[int]
    encryption_key_env: str


@dataclass(frozen=True)
class ScheduleConfig:
    reconcile_interval_sec: int
    active_probe_interval_min: int
    probe_stagger_sec: float
    stale_after_min: int


@dataclass(frozen=True)
class AppConfig:
    discord: DiscordConfig
    security: SecurityConfig
    schedule: ScheduleConfig
    initial_keys: tuple[ApiKey, ...]
    initial_models: tuple[str, ...]


def load_config(path: str | Path) -> AppConfig:
    raw = _expand(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    discord = raw.get("discord", {})
    security = raw.get("security", {})
    schedule = raw.get("schedule", {})
    token = str(discord.get("bot_token", ""))
    channel_id = str(discord.get("channel_id", ""))
    if not token or not channel_id.isdigit():
        raise ValueError("discord.bot_token and numeric discord.channel_id are required")

    keys = tuple(ApiKey(str(item["id"]), str(item["value"])) for item in raw.get("api_keys", []))
    if any(not key.id or not key.value for key in keys):
        raise ValueError("Each configured API key needs non-empty id and value")
    if len({key.id for key in keys}) != len(keys):
        raise ValueError("Duplicate API key IDs in configuration")
    models = tuple(str(model) for model in raw.get("models", []))
    if any(not model.startswith("google/") for model in models):
        raise ValueError("Models must use the google/<model-name> display prefix")
    if len(set(models)) != len(models):
        raise ValueError("Duplicate models in configuration")

    return AppConfig(
        discord=DiscordConfig(token, int(channel_id)),
        security=SecurityConfig(
            frozenset(int(value) for value in security.get("admin_user_ids", [])),
            str(security.get("encryption_key_env", "KEY_ENCRYPTION_SECRET")),
        ),
        schedule=ScheduleConfig(
            int(schedule.get("reconcile_interval_sec", 90)),
            int(schedule.get("active_probe_interval_min", 20)),
            float(schedule.get("probe_stagger_sec", 3)),
            int(schedule.get("stale_after_min", 30)),
        ),
        initial_keys=keys,
        initial_models=models,
    )
