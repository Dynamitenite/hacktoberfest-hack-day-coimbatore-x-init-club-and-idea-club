"""Session and project storage.

* Active sessions (photo bytes, observations) live in memory with a TTL and are
  discarded when the session is deleted or expires. The photo is never written
  to disk unless the user explicitly saves the project.
* SQLite holds the circuit templates and explicitly saved projects.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .catalog import load_templates
from .config import Settings
from .schemas import ImageSession, Observation, Report, utcnow


@dataclass
class SessionState:
    session: ImageSession
    image_jpeg: bytes
    observations: list[Observation] = field(default_factory=list)
    expires_at: datetime = field(default_factory=utcnow)
    rectified_jpeg: bytes | None = None


class SessionStore:
    def __init__(self, ttl_minutes: int) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._items: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = utcnow()
        for sid in [k for k, v in self._items.items() if v.expires_at < now]:
            del self._items[sid]

    def create(self, session: ImageSession, jpeg: bytes) -> SessionState:
        with self._lock:
            self._purge()
            state = SessionState(session=session, image_jpeg=jpeg, expires_at=utcnow() + self._ttl)
            self._items[session.id] = state
            return state

    def get(self, sid: str) -> SessionState | None:
        with self._lock:
            self._purge()
            state = self._items.get(sid)
            if state:
                state.expires_at = utcnow() + self._ttl  # sliding expiry while in use
            return state

    def delete(self, sid: str) -> bool:
        with self._lock:
            return self._items.pop(sid, None) is not None


SCHEMA = """
CREATE TABLE IF NOT EXISTS circuit_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    session_json TEXT NOT NULL,
    observations_json TEXT NOT NULL,
    report_json TEXT,
    image_path TEXT
);
"""


class Database:
    def __init__(self, settings: Settings) -> None:
        self.path = Path(settings.database_path)
        self.saved_dir = Path(settings.saved_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
        self.sync_templates()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def sync_templates(self) -> None:
        """Mirror the validated template files into SQLite (files stay the source of truth)."""
        with self._conn() as c:
            c.execute("DELETE FROM circuit_templates")
            for tpl in load_templates().values():
                c.execute(
                    "INSERT INTO circuit_templates (id, name, body, loaded_at) VALUES (?,?,?,?)",
                    (tpl.id, tpl.name, tpl.model_dump_json(), utcnow().isoformat()),
                )

    def template_ids(self) -> list[str]:
        with self._conn() as c:
            return [r["id"] for r in c.execute("SELECT id FROM circuit_templates ORDER BY name")]

    # ---- explicit saves -------------------------------------------------------
    def save_project(self, name: str, state: SessionState, report: Report | None) -> dict:
        pid = "prj_" + uuid.uuid4().hex[:10]
        image_path = self.saved_dir / f"{pid}.jpg"
        image_path.write_bytes(state.image_jpeg)
        with self._conn() as c:
            c.execute(
                "INSERT INTO saved_projects (id,name,template_id,created_at,session_json,observations_json,report_json,image_path) VALUES (?,?,?,?,?,?,?,?)",
                (
                    pid,
                    name,
                    state.session.circuit_template_id,
                    utcnow().isoformat(),
                    state.session.model_dump_json(),
                    json.dumps([o.model_dump(mode="json") for o in state.observations]),
                    report.model_dump_json() if report else None,
                    str(image_path),
                ),
            )
        return self.get_project_summary(pid)  # type: ignore[return-value]

    def list_projects(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id,name,template_id,created_at FROM saved_projects ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project_summary(self, pid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT id,name,template_id,created_at FROM saved_projects WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def get_project(self, pid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM saved_projects WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def delete_project(self, pid: str) -> bool:
        proj = self.get_project(pid)
        if not proj:
            return False
        with self._conn() as c:
            c.execute("DELETE FROM saved_projects WHERE id=?", (pid,))
        if proj.get("image_path"):
            Path(proj["image_path"]).unlink(missing_ok=True)
        return True
