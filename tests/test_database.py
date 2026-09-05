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
