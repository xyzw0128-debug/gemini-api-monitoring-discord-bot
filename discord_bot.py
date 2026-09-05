"""Discord fixed-message dashboard and administrator-only slash commands."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from database import StateStore
from models import ApiKey

if TYPE_CHECKING:
    from scheduler import ProbeScheduler

ICONS = {"ok": "🟢", "limited": "🔴", "invalid": "⚠️", "unknown": "⚪"}


class MonitorBot(discord.Client):
    def __init__(self, store: StateStore, channel_id: int, admin_ids: frozenset[int]):
        super().__init__(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self)
        self.store, self.channel_id, self.admin_ids = store, channel_id, admin_ids
        self.scheduler: ProbeScheduler | None = None
        self._render_lock = asyncio.Lock()
        self._register_commands()

    def set_scheduler(self, scheduler: "ProbeScheduler") -> None:
        self.scheduler = scheduler

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return not self.admin_ids or interaction.user.id in self.admin_ids

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if self._is_admin(interaction):
            return False
        await interaction.response.send_message("관리자 전용 명령어입니다.", ephemeral=True)
        return True

    def _register_commands(self) -> None:
        key = app_commands.Group(name="key", description="API 키 관리")
        model = app_commands.Group(name="model", description="Gemini 모델 관리")

        @key.command(name="add", description="API 키를 추가합니다.")
        async def add_key(interaction: discord.Interaction, id: str, value: str) -> None:
            if await self._deny(interaction): return
            if self.store.add_key(ApiKey(id, value)):
                await interaction.response.send_message(f"키 `{id}`를 추가했습니다.", ephemeral=True)
                await self.render_dashboard()
            else:
                await interaction.response.send_message("키 ID 또는 키 값이 이미 등록되어 있습니다.", ephemeral=True)

        @key.command(name="remove", description="API 키를 제거합니다.")
        async def remove_key(interaction: discord.Interaction, id: str) -> None:
            if await self._deny(interaction): return
            removed = self.store.remove_key(id)
            await interaction.response.send_message("키를 제거했습니다." if removed else "해당 키 ID가 없습니다.", ephemeral=True)
            if removed: await self.render_dashboard()

        @key.command(name="list", description="등록된 키 ID를 표시합니다.")
        async def list_keys(interaction: discord.Interaction) -> None:
            if await self._deny(interaction): return
            await interaction.response.send_message("등록 키: " + (", ".join(key.id for key in self.store.list_keys()) or "없음"), ephemeral=True)

        @model.command(name="add", description="표시용 google/ 모델을 추가합니다.")
        async def add_model(interaction: discord.Interaction, name: str) -> None:
            if await self._deny(interaction): return
            try: added = self.store.add_model(name)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True); return
            await interaction.response.send_message("모델을 추가했습니다." if added else "이미 등록된 모델입니다.", ephemeral=True)
            if added: await self.render_dashboard()

        @model.command(name="remove", description="모델을 제거합니다.")
        async def remove_model(interaction: discord.Interaction, name: str) -> None:
            if await self._deny(interaction): return
            removed = self.store.remove_model(name)
            await interaction.response.send_message("모델을 제거했습니다." if removed else "해당 모델이 없습니다.", ephemeral=True)
            if removed: await self.render_dashboard()

        @model.command(name="list", description="등록된 모델을 표시합니다.")
        async def list_models(interaction: discord.Interaction) -> None:
            if await self._deny(interaction): return
            await interaction.response.send_message("등록 모델: " + (", ".join(self.store.list_models()) or "없음"), ephemeral=True)

        @self.tree.command(name="refresh", description="전체 키/모델 조합을 즉시 재확인합니다.")
        async def refresh(interaction: discord.Interaction) -> None:
            if await self._deny(interaction): return
            await interaction.response.send_message("전체 재확인을 시작했습니다. 요청은 순차적으로 전송됩니다.", ephemeral=True)
            if self.scheduler: asyncio.create_task(self.scheduler.refresh_all())

        self.tree.add_command(key); self.tree.add_command(model)

    def _embed(self) -> discord.Embed:
        keys, models = self.store.list_keys(), self.store.list_models()
        by_model = defaultdict(dict)
        for row in self.store.rows(): by_model[row["model_id"]][row["key_id"]] = row
        lines, statuses = [], []
        for model in models:
            records = by_model[model]
            row_statuses = [records.get(key.id, {"status": "unknown"})["status"] for key in keys]
            statuses.extend(row_statuses)
            limited = sum(status == "limited" for status in row_statuses)
            label = model.removeprefix("google/").replace("-", " ").title()
            lines.append(f"`{label:<30}` {''.join(ICONS[status] for status in row_statuses)}  ({limited}/{len(keys)} 제한)")
        color = discord.Color.green() if statuses and all(status == "ok" for status in statuses) else (discord.Color.red() if any(status in {"limited", "invalid"} for status in statuses) else discord.Color.orange())
        embed = discord.Embed(title="Gemini API Key Limit Monitor", description="\n".join(lines) or "등록된 키와 모델이 없습니다.", color=color, timestamp=datetime.now(UTC))
        embed.set_footer(text="키 순서: " + (" · ".join(f"{index + 1}={key.id}" for index, key in enumerate(keys)) or "없음") + " | 🟢 정상 · 🔴 제한 · ⚠️ 오류 · ⚪ 미확인/재확인 대기")
        return embed

    async def render_dashboard(self) -> None:
        async with self._render_lock:
            embed = self._embed()
            signature = f"{embed.title}|{embed.description}|{embed.colour.value}|{embed.footer.text}"
            if signature == self.store.get_app_state("render_signature"):
                return
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(self.channel_id)
            message_id = self.store.get_app_state("status_message_id")
            try:
                message = await channel.fetch_message(int(message_id)) if message_id else None
            except (discord.NotFound, ValueError):
                message = None
            if message is None:
                message = await channel.send(embed=embed)
                self.store.set_app_state("status_message_id", str(message.id))
            else:
                await message.edit(embed=embed)
            self.store.set_app_state("render_signature", signature)

    async def on_ready(self) -> None:
        await self.tree.sync()
        await self.render_dashboard()
