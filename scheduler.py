"""Serialized, staggered probe execution and time-only reconciliation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
from typing import Awaitable, Callable

import aiohttp

from database import StateStore
from monitor_logging import log_event
from probe import probe_key_model

Render = Callable[[], Awaitable[None]]


@dataclass
class ProbeJob:
    source: str
    total: int
    completed: int = 0
    running: bool = False


class ProbeScheduler:
    def __init__(
        self, store: StateStore, active_minutes: int, reconcile_seconds: int, stagger_seconds: float,
        stale_minutes: int, render: Render, model_key_parallelism: int = 5,
    ):
        self.store, self.active_minutes, self.reconcile_seconds = store, active_minutes, reconcile_seconds
        self.stagger_seconds, self.stale_minutes, self.render = stagger_seconds, stale_minutes, render
        self.model_key_parallelism = model_key_parallelism
        self.lock = asyncio.Lock()
        self._jobs: dict[asyncio.Task, ProbeJob] = {}
        self._resetting = False

    def _start(self, targets: list[tuple], source: str, *, stagger: bool = True) -> asyncio.Task | None:
        """Start one cancellable probe job, unless a reset is in progress."""
        if not targets or self._resetting or self.has_job(source):
            return None
        job = ProbeJob(source=source, total=len(targets))
        task = asyncio.create_task(self._probe(targets, job, stagger=stagger), name=f"probe:{source}")
        self._jobs[task] = job
        task.add_done_callback(self._jobs.pop)
        return task

    async def _probe(self, targets: list[tuple], job: ProbeJob, *, stagger: bool = True) -> None:
        retry_sec = int(self.store.get_app_state("retry_seconds") or "1800")

        try:
            log_event("probe_job_started", source=job.source, target_count=job.total)
            async with self.lock, aiohttp.ClientSession() as session:
                job.running = True
                by_model: dict[str, list] = {}
                for key, model in targets:
                    by_model.setdefault(model, []).append(key)
                for index, (model, keys) in enumerate(by_model.items()):
                    if index and stagger:
                        await asyncio.sleep(self.stagger_seconds)
                    semaphore = asyncio.Semaphore(self.model_key_parallelism)
                    await asyncio.gather(*(
                        self._probe_one(session, key, model, job, retry_sec, semaphore)
                        for key in keys
                    ))
        except asyncio.CancelledError:
            # reset() collects every cancelled job before it clears all transient states once.
            raise
        finally:
            log_event("probe_job_finished", source=job.source, completed_count=job.completed, target_count=job.total)

    async def _probe_one(
        self, session: aiohttp.ClientSession, key, model: str, job: ProbeJob, retry_sec: int,
        semaphore: asyncio.Semaphore,
    ) -> None:
        async with semaphore:
            self.store.mark_checking(key.id, model)
            log_event("probe_started", source=job.source, key_id=key.id, model_id=model)
            await self.render()
            result = await probe_key_model(session, key.id, key.value, model, default_retry_sec=retry_sec)
            self.store.record(result, job.source)
            log_event(
                "probe_finished", source=job.source, key_id=key.id, model_id=model,
                outcome=result.status, http_status=result.http_status, latency_ms=result.latency_ms,
                limit_type=result.limit_type, reset_at=result.reset_at, error_type=result.error_type,
            )
            job.completed += 1
            await self.render()

    def status(self) -> list[ProbeJob]:
        return list(self._jobs.values())

    def has_job(self, source: str) -> bool:
        return any(job.source == source for job in self._jobs.values())

    async def reset(self) -> tuple[int, int]:
        """Cancel every running or queued probe and clear transient checking states."""
        self._resetting = True
        try:
            tasks = list(self._jobs)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            reset_states = self.store.reset_checking_to_unknown()
            await self.render()
            return len(tasks), reset_states
        finally:
            self._resetting = False

    def refresh_all(self) -> asyncio.Task | None:
        return self._start(self.store.all_targets(), "전체 재확인")

    def refresh_models(self, model_ids: set[str], key_limit: int | None = None) -> asyncio.Task | None:
        models = ", ".join(sorted(model_ids))
        return self._start(self.store.targets_for_models(model_ids, key_limit), f"OpenClaw 모델 재확인: {models}")

    def refresh_key(self, key_id: str) -> asyncio.Task | None:
        targets = [(k, m) for k, m in self.store.all_targets() if k.id == key_id]
        return self._start(targets, f"키 재확인: {key_id}")

    def refresh_model(self, model_id: str) -> asyncio.Task | None:
        targets = [(k, m) for k, m in self.store.all_targets() if m == model_id]
        return self._start(targets, f"모델 재확인: {model_id}")

    async def active_loop(self) -> None:
        while True:
            stale_before = datetime.now(UTC) - timedelta(minutes=self.stale_minutes)
            task = self._start(self.store.probe_targets(stale_before), "자동 재확인")
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await asyncio.sleep(self.active_minutes * 60)

    async def reconcile_loop(self) -> None:
        while True:
            now = datetime.now(UTC)
            changed = self.store.mark_expired_for_recheck(now)
            changed = bool(self.store.prune_runtime_events(now=now)) or changed
            changed = bool(self.store.prune_probe_events(now=now)) or changed
            if changed:
                await self.render()
            await asyncio.sleep(self.reconcile_seconds)
