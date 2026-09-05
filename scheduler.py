"""Serialized, staggered probe execution and time-only reconciliation."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
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

    async def probe(self, targets: list[tuple], *, stagger: bool = True) -> None:
        async with self.lock, aiohttp.ClientSession() as session:
            for index, (key, model) in enumerate(targets):
                if index and stagger:
                    await asyncio.sleep(self.stagger_seconds)
                self.store.record(await probe_key_model(session, key.id, key.value, model))
                await self.render()

    async def refresh_all(self) -> None:
        await self.probe(self.store.all_targets())

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
