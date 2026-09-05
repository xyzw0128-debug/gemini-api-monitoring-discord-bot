from datetime import UTC, datetime, timedelta

from probe import DEFAULT_RETRY_SECONDS, api_model_name, parse_quota_error, parse_retry_delay


def test_display_prefix_is_removed_for_google_api() -> None:
    assert api_model_name("google/gemini-3.6-flash") == "gemini-3.6-flash"


def test_retry_delay_parsing() -> None:
    assert parse_retry_delay("15s") == 15
    assert parse_retry_delay("1.5s") == 1.5
    assert parse_retry_delay("bad") is None


def test_quota_parsing_preserves_quota_id_and_model() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerMinute", "quotaDimensions": {"model": "gemini-3.6-flash"}}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "15s"},
    ]}}
    limit_type, reset_at = parse_quota_error(payload, now)
    assert "quotaId=GenerateRequestsPerMinute" in limit_type
    assert "model=gemini-3.6-flash" in limit_type
    assert reset_at == now + timedelta(seconds=15)


def test_short_429_uses_conservative_default() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_quota_error({}, now) == ("unknown", now + timedelta(seconds=DEFAULT_RETRY_SECONDS))
