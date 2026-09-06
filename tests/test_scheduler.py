import asyncio

from cryptography.fernet import Fernet

from database import StateStore
from models import ApiKey
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
        assert scheduler.refresh_all() is not None
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
