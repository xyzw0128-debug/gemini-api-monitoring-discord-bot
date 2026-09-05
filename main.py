"""Application entry point."""
from __future__ import annotations

import asyncio
import os

from config import load_config
from database import StateStore
from discord_bot import MonitorBot
from scheduler import ProbeScheduler


async def run() -> None:
    config = load_config(os.environ.get("MONITOR_CONFIG", "config.yaml"))
    store = StateStore(os.environ.get("MONITOR_DB", "monitor.db"), os.environ.get(config.security.encryption_key_env, ""))
    store.bootstrap(config.initial_keys, config.initial_models)
    bot = MonitorBot(store, config.discord.channel_id, config.security.admin_user_ids)
    scheduler = ProbeScheduler(store, config.schedule.active_probe_interval_min, config.schedule.reconcile_interval_sec, config.schedule.probe_stagger_sec, config.schedule.stale_after_min, bot.render_dashboard)
    bot.set_scheduler(scheduler)
    async with bot:
        asyncio.create_task(scheduler.active_loop())
        asyncio.create_task(scheduler.reconcile_loop())
        await bot.start(config.discord.bot_token)


if __name__ == "__main__":
    asyncio.run(run())
