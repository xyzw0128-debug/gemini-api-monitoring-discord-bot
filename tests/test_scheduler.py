import asyncio
from datetime import UTC, datetime

from cryptography.fernet import Fernet

from database import StateStore
from models import ApiKey, ProbeResult
from scheduler import ProbeScheduler


def test_reset_cancels_running_probe_and_clears_checking_state(tmp_path, monkeypatch) -> None:
    async def scenario() -> None:
        store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
        store.bootstrap((ApiKey("one", "secret"),), ("google/gemini-test",))
        started = asyncio.Event()

        async def render() -> None:
            return None

        async def slow_probe(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr("scheduler.probe_key_model", slow_probe)
        scheduler = ProbeScheduler(store, 20, 90, 0, 30, render)
        assert scheduler.refresh_models({"google/gemini-test"}) is not None
        await started.wait()
        assert scheduler.refresh_all() is not None
        await asyncio.sleep(0)
        assert sorted(job.running for job in scheduler.status()) == [False, True]

        cancelled, reset_states = await scheduler.reset()

        assert cancelled == 2
        assert reset_states == 1
        assert scheduler.status() == []
        assert store.rows()[0]["status"] == "unknown"

    asyncio.run(scenario())


def test_duplicate_refresh_is_not_queued(tmp_path, monkeypatch) -> None:
    async def scenario() -> None:
        store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
        store.bootstrap((ApiKey("one", "secret"),), ("google/gemini-test",))
        started = asyncio.Event()

        async def render() -> None:
            return None

        async def slow_probe(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr("scheduler.probe_key_model", slow_probe)
        scheduler = ProbeScheduler(store, 20, 90, 0, 30, render)
        assert scheduler.refresh_all() is not None
        await started.wait()
        assert scheduler.has_job("전체 재확인")
        assert scheduler.refresh_all() is None
        assert len(scheduler.status()) == 1
        await scheduler.reset()

    asyncio.run(scenario())


def test_full_refresh_parallelizes_keys_within_one_model(tmp_path, monkeypatch) -> None:
    async def scenario() -> None:
        store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
        store.bootstrap(
            (ApiKey("one", "secret-one"), ApiKey("two", "secret-two")),
            ("google/gemini-a", "google/gemini-b"),
        )
        started: list[tuple[str, str]] = []
        first_model_started = asyncio.Event()
        release = asyncio.Event()

        async def render() -> None:
            return None

        async def slow_probe(_, key_id, __, model_id, **___):
            started.append((key_id, model_id))
            if len(started) == 2:
                first_model_started.set()
            await release.wait()
            return ProbeResult(key_id, model_id, "ok", None, None, datetime.now(UTC), None, 200, 1)

        monkeypatch.setattr("scheduler.probe_key_model", slow_probe)
        scheduler = ProbeScheduler(store, 20, 90, 0, 30, render, model_key_parallelism=2)
        task = scheduler.refresh_all()
        assert task is not None
        await first_model_started.wait()
        assert {model for _, model in started} == {"google/gemini-a"}
        release.set()
        await task
        assert [model for _, model in started] == ["google/gemini-a", "google/gemini-a", "google/gemini-b", "google/gemini-b"]

    asyncio.run(scenario())
