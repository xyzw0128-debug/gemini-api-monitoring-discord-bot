"""Shared immutable domain models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Status = Literal["ok", "limited", "invalid", "unknown", "checking"]


@dataclass(frozen=True)
class ApiKey:
    id: str
    value: str


@dataclass(frozen=True)
class ProbeResult:
    key_id: str
    model_id: str
    status: Status
    limit_type: str | None
    reset_at: datetime | None
    checked_at: datetime
    raw_message: str | None
