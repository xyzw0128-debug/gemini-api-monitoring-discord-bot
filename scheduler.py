"""Serialized, staggered probe execution and time-only reconciliation."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
from typing import Awaitable, Callable

import aiohttp

from database import StateStore
from probe import probe_key_model

Render = Callable[[], Awaitable[None]]


class ProbeScheduler:
    def __init__(self, store: StateStore, active_minutes: int, reconcile_seconds: int, stagger_seconds: float, stale_minutes: int, render: Render):
        self.store, self.active_minutes, self.reconcile_seconds = store, active_minutes, reconcile_seconds
        self.stagger_seconds, self.stale_minutes, self.render = stagger_seconds, stale_minutes, render
        self.lock = asyncio.Lock()
        self.current_task: asyncio.Task | None = None

    async def probe(self, targets: list[tuple], *, stagger: bool = True) -> None:
        if not targets:
            return

        # 현재 실행 중인 asyncio 태스크를 자동으로 저장해서 /stop 으로 취소 가능하게 만듦
        self.current_task = asyncio.current_task()
        retry_sec = int(self.store.get_app_state("retry_seconds") or "1800")

        try:
            async with self.lock, aiohttp.ClientSession() as session:
                for index, (key, model) in enumerate(targets):
                    if index and stagger:
                        await asyncio.sleep(self.stagger_seconds)

                    self.store.mark_checking(key.id, model)
                    await self.render()

                    result = await probe_key_model(session, key.id, key.value, model, default_retry_sec=retry_sec)
                    self.store.record(result)
                    await self.render()
        except asyncio.CancelledError:
            # /stop 으로 중단되었을 때 '🔵(확인 중)'으로 남아있는 항목을 '⚪(미확인)'으로 깔끔하게 원복
            self.store.reset_checking_to_unknown()
            await self.render()
            raise
        finally:
            if self.current_task == asyncio.current_task():
                self.current_task = None

    def cancel_current(self) -> bool:
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            return True
        return False

    async def refresh_all(self) -> None:
        await self.probe(self.store.all_targets())

    async def refresh_models(self, model_ids: set[str]) -> None:
        await self.probe(self.store.targets_for_models(model_ids))

    async def refresh_key(self, key_id: str) -> None:
        targets = [(k, m) for k, m in self.store.all_targets() if k.id == key_id]
        if targets:
            await self.probe(targets)
    async def refresh_model(self, model_id: str) -> None:
        targets = [(k, m) for k, m in self.store.all_targets() if m == model_id]
        if targets:
            await self.probe(targets)

    async def active_loop(self) -> None:
        while True:
            stale_before = datetime.now(UTC) - timedelta(minutes=self.stale_minutes)
            await self.probe(self.store.probe_targets(stale_before))
            await asyncio.sleep(self.active_minutes * 60)

    async def reconcile_loop(self) -> None:
        while True:
            if self.store.mark_expired_for_recheck(datetime.now(UTC)):
                await self.render()
            await asyncio.sleep(self.reconcile_seconds)
