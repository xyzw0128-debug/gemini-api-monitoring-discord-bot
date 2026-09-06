"""Low-cost Gemini countTokens availability probe."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from models import ProbeResult
KST = ZoneInfo("Asia/Seoul")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_RETRY_SECONDS = 1800
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)s$")


def api_model_name(display_model: str) -> str:
    """Remove the display-only provider prefix before calling Google's API."""
    return display_model.removeprefix("google/")


def parse_retry_delay(value: str | None) -> float | None:
    match = _DURATION.match(value or "")
    return float(match.group(1)) if match else None


def parse_quota_error(payload: object, now: datetime, default_retry_sec: int = 1800) -> tuple[str, datetime]:
    details = payload.get("error", {}).get("details", []) if isinstance(payload, dict) else []
    quota_parts: list[str] = []
    retry_seconds: float | None = None
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if detail.get("@type", "").endswith("RetryInfo"):
            retry_seconds = parse_retry_delay(detail.get("retryDelay"))
        if detail.get("@type", "").endswith("QuotaFailure"):
            for violation in detail.get("violations", []):
                if not isinstance(violation, dict):
                    continue
                quota_id = violation.get("quotaId")
                model = violation.get("quotaDimensions", {}).get("model")
                if quota_id is not None:
                    quota_parts.append(f"quotaId={quota_id}")
                if model is not None:
                    quota_parts.append(f"model={model}")
                    
    cooldown = max(retry_seconds or 0, default_retry_sec)
    return ("; ".join(quota_parts) or "unknown", now + timedelta(seconds=cooldown))


async def probe_key_model(
    session: aiohttp.ClientSession, key_id: str, key_value: str, model_id: str, default_retry_sec: int = 1800
) -> ProbeResult:
    checked_at = datetime.now(UTC)
    try:
        async with session.post(
            API_URL.format(model=api_model_name(model_id)),
            params={"key": key_value},
            json={
                "contents": [{"parts": [{"text": "ping"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            raw = (await response.text())[:1000]
            if response.status == 200:
                return ProbeResult(key_id, model_id, "ok", None, None, checked_at, None)
            if response.status == 429:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                limit_type, reset_at = parse_quota_error(payload, checked_at, default_retry_sec)
                return ProbeResult(key_id, model_id, "limited", limit_type, reset_at, checked_at, raw)
            if response.status in {401, 403, 404}:
                return ProbeResult(key_id, model_id, "invalid", None, None, checked_at, raw)
            return ProbeResult(key_id, model_id, "unknown", None, None, checked_at, raw)
    except (aiohttp.ClientError, TimeoutError) as exc:
        return ProbeResult(key_id, model_id, "unknown", None, None, checked_at, str(exc)[:1000])
