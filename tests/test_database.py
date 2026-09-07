from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet

from database import StateStore
from models import ApiKey, ProbeResult


def test_duplicate_key_value_is_rejected_and_matrix_is_dynamic(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    assert store.add_model("google/gemini-a")
    assert store.add_key(ApiKey("one", "secret"))
    assert not store.add_key(ApiKey("two", "secret"))
    assert store.add_model("google/gemini-b")
    assert len(store.rows()) == 2


def test_expired_limit_needs_probe_before_ok(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    store.bootstrap((ApiKey("one", "secret"),), ("google/gemini-a",))
    now = datetime.now(UTC)
    store.record(ProbeResult("one", "google/gemini-a", "limited", "unknown", now - timedelta(seconds=1), now, None))
    assert store.mark_expired_for_recheck(now)
    row = store.rows()[0]
    assert row["status"] == "unknown"
    assert row["recheck_pending"] == 1


def test_runtime_events_older_than_thirty_minutes_are_removed(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.record_runtime_event("google/gemini-a", "429", "old", now - timedelta(minutes=31))
    store.record_runtime_event("google/gemini-a", "429", "new", now - timedelta(minutes=29))

    assert store.prune_runtime_events(now=now) == 1
    events = store.recent_runtime_events(now=now)

    assert [event["message"] for event in events] == ["new"]


def test_limited_target_waits_for_reset_and_probe_events_expire(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    store.bootstrap((ApiKey("one", "secret"),), ("google/gemini-a",))
    now = datetime.now(UTC)
    store.record(ProbeResult("one", "google/gemini-a", "limited", "quota", now + timedelta(hours=1), now, "429", 429, 12))

    assert store.probe_targets(now + timedelta(minutes=1)) == []
    event = store.db.execute("SELECT job_source, http_status FROM probe_events").fetchone()
    assert (event["job_source"], event["http_status"]) == ("unspecified", 429)
    assert store.prune_probe_events(now=now + timedelta(days=31)) == 1


def test_all_targets_are_grouped_by_model_then_key(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    store.bootstrap(
        (ApiKey("one", "secret-one"), ApiKey("two", "secret-two")),
        ("google/gemini-a", "google/gemini-b"),
    )
    assert [(key.id, model) for key, model in store.all_targets()] == [
        ("one", "google/gemini-a"), ("two", "google/gemini-a"),
        ("one", "google/gemini-b"), ("two", "google/gemini-b"),
    ]
