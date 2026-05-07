from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import DATA_DIR, SQLITE_DB_PATH


class AgentRegistrationRequest(BaseModel):
    agent_name: str
    purpose: Optional[str] = None
    registration_code: Optional[str] = None

    @field_validator("agent_name")
    @classmethod
    def _agent_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("agent_name must not be blank")
        return value


class AgentRegistrationResponse(BaseModel):
    agent_id: str
    api_key: str
    key_type: str = "Bearer"
    note: str = "Store this key now; it is shown only once."


class AgentAuthStore:
    def __init__(self, path: Path | None = None, db_path: Path | None = None):
        self.path = path or (DATA_DIR / "agents.json")
        self.db_path = Path(db_path) if db_path is not None else SQLITE_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_json_if_present()

    def register(self, request: AgentRegistrationRequest) -> AgentRegistrationResponse:
        required_code = os.getenv("ACTVOICE_REGISTRATION_CODE")
        if required_code and request.registration_code != required_code:
            raise PermissionError("invalid registration_code")

        agent_id = secrets.token_urlsafe(12)
        api_key = "av_" + secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents (agent_id, agent_name, purpose, key_hash, created_at, revoked)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (agent_id, request.agent_name, request.purpose, self.hash_key(api_key), now),
            )
        return AgentRegistrationResponse(agent_id=agent_id, api_key=api_key)

    def verify(self, api_key: str) -> bool:
        if not api_key:
            return False
        key_hash = self.hash_key(api_key)
        with self._connect() as conn:
            rows = conn.execute("SELECT key_hash FROM agents WHERE revoked = 0").fetchall()
        return any(secrets.compare_digest(row["key_hash"], key_hash) for row in rows)

    @staticmethod
    def hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    purpose TEXT,
                    key_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def _migrate_json_if_present(self) -> None:
        if not self.path.exists():
            return
        try:
            records: Dict[str, Dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        with self._connect() as conn:
            for agent_id, record in records.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO agents
                        (agent_id, agent_name, purpose, key_hash, created_at, revoked)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.get("agent_id") or agent_id,
                        record.get("agent_name") or "Migrated agent",
                        record.get("purpose"),
                        record.get("key_hash") or "",
                        record.get("created_at") or datetime.now(timezone.utc).isoformat(),
                        1 if record.get("revoked") else 0,
                    ),
                )
