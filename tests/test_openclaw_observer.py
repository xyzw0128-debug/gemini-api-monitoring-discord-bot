import asyncio

from cryptography.fernet import Fernet

from database import StateStore
from models import ApiKey
from openclaw_observer import OpenClawObserver, parse_openclaw_google_event


class FakeScheduler:
    def __init__(self) -> None:
        self.models: list[set[str]] = []

    def refresh_models(self, model_ids: set[str]) -> None:
        self.models.append(model_ids)


def test_parser_only_accepts_relevant_google_events() -> None:
    assert parse_openclaw_google_event("info provider=google model=gemini-3.6-flash status=429") == ("gemini-3.6-flash", "429")
    assert parse_openclaw_google_event("warn provider=google model=gemini-3.5-flash status=503") == ("gemini-3.5-flash", "overloaded")
    assert parse_openclaw_google_event("warn provider=openai model=gpt status=429") is None
    assert parse_openclaw_google_event("warn provider=google status=429") is None


def test_observer_records_once_and_prioritizes_matching_model(tmp_path) -> None:
    async def scenario() -> None:
        store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
        store.bootstrap((ApiKey("one", "secret"),), ("google/gemini-3.6-flash",))
        scheduler = FakeScheduler()
        renders = 0

        async def render() -> None:
            nonlocal renders
            renders += 1

        observer = OpenClawObserver(store, scheduler, ("openclaw", "logs", "--follow"), 1, 60, render)
        line = "info provider=google model=gemini-3.6-flash status=429"
        assert await observer.handle_line(line)
        await asyncio.sleep(0)
        assert not await observer.handle_line(line)
        assert scheduler.models == [{"google/gemini-3.6-flash"}]
        assert store.recent_runtime_events()[0]["kind"] == "429"
        assert renders == 1

    asyncio.run(scenario())
