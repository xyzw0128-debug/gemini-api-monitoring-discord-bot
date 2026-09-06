from cryptography.fernet import Fernet

from database import StateStore
from discord_bot import MonitorBot
from models import ApiKey


def test_dashboard_footer_has_a_readable_second_line_and_compact_model_spacing(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    store.bootstrap(
        (ApiKey("1", "key-one"), ApiKey("2", "key-two")),
        ("google/gemini-3.6-flash", "google/gemini-3.1-flash-lite"),
    )
    bot = MonitorBot(store, 1, frozenset())
    embed = bot._embed()
    assert embed.footer.text.startswith("키 순서: 1=1 · 2=2\n🟢 정상")
    rows = embed.description.splitlines()
    assert "`Gemini 3.6 Flash     `   ⚪⚪" in rows[0]


def test_dashboard_has_persistent_clickable_probe_controls(tmp_path) -> None:
    store = StateStore(tmp_path / "monitor.db", Fernet.generate_key().decode())
    bot = MonitorBot(store, 1, frozenset({123}))
    controls = bot.dashboard_controls

    assert controls.timeout is None
    assert [(child.label, child.custom_id) for child in controls.children] == [
        ("전체 재확인", "monitor:refresh"),
        ("작업 상태", "monitor:status"),
        ("RESET", "monitor:reset"),
    ]
