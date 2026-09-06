"""Optional passive observer for OpenClaw real-use Google failures.

It never changes a key's final status from a log line. Instead it records a
model-level event and schedules countTokens probes for that model's known keys.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from database import StateStore
from scheduler import ProbeScheduler

_MODEL = re.compile(r"\bmodel=([A-Za-z0-9._-]+)")


def parse_openclaw_google_event(line: str) -> tuple[str, str] | None:
    """Extract a supported Google model event without retaining sensitive log data."""
    if "provider=google" not in line:
        return None
    model_match = _MODEL.search(line)
    if not model_match:
        return None
    if "status=429" in line:
        kind = "429"
    elif "status=503" in line or "reason=overloaded" in line:
        kind = "overloaded"
    elif "first response retry deadline reached" in line or "LLM idle timeout" in line:
        kind = "timeout"
    else:
        return None
    return model_match.group(1), kind


class OpenClawObserver:
    def __init__(
        self,
        store: StateStore,
        scheduler: ProbeScheduler,
        command: tuple[str, ...],
        restart_delay_sec: int,
        cooldown_sec: int,
        render: Callable[[], Awaitable[None]],
    ):
        self.store, self.scheduler, self.command = store, scheduler, command
        self.restart_delay_sec, self.cooldown_sec, self.render = restart_delay_sec, cooldown_sec, render
        self._last_seen: dict[tuple[str, str], datetime] = {}

    async def handle_line(self, line: str) -> bool:
        event = parse_openclaw_google_event(line)
        if event is None:
            return False
        pure_model, kind = event
        model_id = f"google/{pure_model}"
        if model_id not in self.store.list_models():
            return False
        now = datetime.now(UTC)
        key = (model_id, kind)
        if now - self._last_seen.get(key, now - timedelta(seconds=self.cooldown_sec + 1)) < timedelta(seconds=self.cooldown_sec):
            return False
        self._last_seen[key] = now
        self.store.record_runtime_event(model_id, kind, f"OpenClaw {kind} 감지", now)
        await self.render()
        self.scheduler.refresh_models({model_id})
        return True

    async def run(self) -> None:
        while True:
            try:
                process = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert process.stdout is not None
                async for raw_line in process.stdout:
                    await self.handle_line(raw_line.decode(errors="replace").strip())
                await process.wait()
            except (FileNotFoundError, OSError):
                # Keep the Discord probe bot running even when OpenClaw is unavailable.
                pass
            await asyncio.sleep(self.restart_delay_sec)
