import os


def test_monitor_db_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_DB", "/var/lib/gemini-api-monitor/monitor.db")
    assert os.environ.get("MONITOR_DB", "monitor.db") == "/var/lib/gemini-api-monitor/monitor.db"
