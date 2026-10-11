"""Mock authorised registry: a SEPARATE SQLite file holding synthetic identity records only
(no wellbeing data). Stands in for the e-Prisons / NHAA-Integrated-Portal interface."""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .base import IdentityConnector, IdentityResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS registry_persons (
    person_id TEXT PRIMARY KEY,
    external_ref TEXT NOT NULL,
    display_name TEXT NOT NULL,
    group_code TEXT NOT NULL,
    language_pref TEXT NOT NULL,
    record_status TEXT NOT NULL,          -- active | released | transferred | closed
    context_note TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS registry_events (
    event_id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    event_date TEXT NOT NULL,
    label TEXT NOT NULL
);
"""


class MockRegistryConnector(IdentityConnector):
    def __init__(self, path: Path, source_label: str):
        self.path = Path(path)
        self.source_label = source_label

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def init_schema(self):
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def load(self, persons: List[Dict], events: List[Dict]):
        self.init_schema()
        with self._conn() as c:
            c.execute("DELETE FROM registry_persons")
            c.execute("DELETE FROM registry_events")
            c.executemany(
                "INSERT INTO registry_persons VALUES (:person_id,:external_ref,:display_name,:group_code,"
                ":language_pref,:record_status,:context_note,1)", persons)
            c.executemany("INSERT INTO registry_events VALUES (:event_id,:person_id,:event_date,:label)", events)

    def lookup(self, person_id: str) -> IdentityResult:
        pid = (person_id or "").strip().upper()
        if not pid or len(pid) > 20 or not pid.replace("-", "").isalnum():
            return IdentityResult("not_found", None, self.source_label)
        if not self.path.exists():
            return IdentityResult("unavailable", None, self.source_label)
        with self._conn() as c:
            row = c.execute("SELECT * FROM registry_persons WHERE person_id=?", (pid,)).fetchone()
        if row is None:
            return IdentityResult("not_found", None, self.source_label)
        if row["record_status"] != "active":
            # never fabricate or reveal identity details for an unavailable record
            return IdentityResult("unavailable", None, self.source_label)
        return IdentityResult("found", dict(row), self.source_label)

    def events_for(self, person_id: str) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM registry_events WHERE person_id=? ORDER BY event_date", (person_id,)).fetchall()
        return [dict(r) for r in rows]


def get_connector() -> MockRegistryConnector:
    from .. import config
    from ..profiles import get_profile
    return MockRegistryConnector(config.MOCK_REGISTRY_PATH, get_profile(config.PROFILE)["identity_source"])
