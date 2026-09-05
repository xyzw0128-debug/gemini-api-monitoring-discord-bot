"""SQLite persistence for encrypted keys, models, probe state, and Discord message state."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from models import ApiKey, ProbeResult


class StateStore:
    def __init__(self, path: str | Path, encryption_secret: str):
        if not encryption_secret:
            raise ValueError("The encryption key environment variable is required")
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.fernet = Fernet(encryption_secret.encode())
        self._create_schema()

    def _create_schema(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
          id TEXT PRIMARY KEY, encrypted_value BLOB NOT NULL, fingerprint TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS probe_state (
          key_id TEXT NOT NULL, model_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'unknown',
          limit_type TEXT, reset_at TEXT, last_checked TEXT, raw_message TEXT, recheck_pending INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(key_id, model_id), FOREIGN KEY(key_id) REFERENCES api_keys(id), FOREIGN KEY(model_id) REFERENCES models(id));
        CREATE TABLE IF NOT EXISTS app_state (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def add_key(self, key: ApiKey) -> bool:
        try:
            self.db.execute("INSERT INTO api_keys VALUES (?, ?, ?, ?)", (key.id, self.fernet.encrypt(key.value.encode()), self._fingerprint(key.value), self._now()))
        except sqlite3.IntegrityError:
            return False
        self._ensure_matrix()
        self.db.commit()
        return True

    def remove_key(self, key_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        self.db.execute("DELETE FROM probe_state WHERE key_id = ?", (key_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def list_keys(self) -> list[ApiKey]:
        rows = self.db.execute("SELECT id, encrypted_value FROM api_keys ORDER BY created_at, id").fetchall()
        return [ApiKey(row["id"], self.fernet.decrypt(row["encrypted_value"]).decode()) for row in rows]

    def add_model(self, model_id: str) -> bool:
        if not model_id.startswith("google/"):
            raise ValueError("Model must start with google/")
        try:
            self.db.execute("INSERT INTO models VALUES (?, ?)", (model_id, self._now()))
        except sqlite3.IntegrityError:
            return False
        self._ensure_matrix()
        self.db.commit()
        return True

    def remove_model(self, model_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        self.db.execute("DELETE FROM probe_state WHERE model_id = ?", (model_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def list_models(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT id FROM models ORDER BY created_at, id")]

    def _ensure_matrix(self) -> None:
        self.db.execute("""INSERT OR IGNORE INTO probe_state(key_id, model_id)
          SELECT api_keys.id, models.id FROM api_keys CROSS JOIN models""")

    def bootstrap(self, keys: tuple[ApiKey, ...], models: tuple[str, ...]) -> None:
        for key in keys:
            self.add_key(key)
        for model in models:
            self.add_model(model)
        self._ensure_matrix()
        self.db.commit()

    def record(self, result: ProbeResult) -> None:
        self.db.execute("""UPDATE probe_state SET status=?, limit_type=?, reset_at=?, last_checked=?, raw_message=?, recheck_pending=0
          WHERE key_id=? AND model_id=?""", (result.status, result.limit_type, result.reset_at.isoformat() if result.reset_at else None, result.checked_at.isoformat(), result.raw_message, result.key_id, result.model_id))
        self.db.commit()

    def mark_expired_for_recheck(self, now: datetime) -> bool:
        cursor = self.db.execute("""UPDATE probe_state SET recheck_pending=1, status='unknown'
          WHERE status='limited' AND reset_at IS NOT NULL AND reset_at <= ?""", (now.isoformat(),))
        self.db.commit()
        return cursor.rowcount > 0

    def probe_targets(self, stale_before: datetime) -> list[tuple[ApiKey, str]]:
        rows = self.db.execute("""SELECT k.id, k.encrypted_value, p.model_id FROM probe_state p
          JOIN api_keys k ON k.id=p.key_id WHERE p.recheck_pending=1 OR p.last_checked IS NULL OR p.last_checked <= ?
          ORDER BY p.recheck_pending DESC, p.last_checked""", (stale_before.isoformat(),)).fetchall()
        return [(ApiKey(row["id"], self.fernet.decrypt(row["encrypted_value"]).decode()), row["model_id"]) for row in rows]

    def all_targets(self) -> list[tuple[ApiKey, str]]:
        return [(key, model) for key in self.list_keys() for model in self.list_models()]

    def rows(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM probe_state ORDER BY model_id, key_id").fetchall()

    def get_app_state(self, name: str) -> str | None:
        row = self.db.execute("SELECT value FROM app_state WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def set_app_state(self, name: str, value: str) -> None:
        self.db.execute("INSERT INTO app_state VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (name, value))
        self.db.commit()
