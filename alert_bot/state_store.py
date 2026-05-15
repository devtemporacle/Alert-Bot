"""SQLite-backed state: dedup, decisions, manual trade log.

Tables (per strategy_3_alert_bot.md):
  candidates_seen  — every contract we've evaluated, with last seen time + score
  alerts_sent      — alerts actually pushed to Telegram (with full snapshot json)
  decisions        — Approve/Skip/Snooze callbacks from the user
  trades           — manually-entered entry/exit data; the validation dataset

Design notes for someone coming from .NET:
  - sqlite3 is stdlib. No ORM in v1; raw parameterized SQL is fine for this
    schema size (~4 tables) and keeps the data layer transparent.
  - Connections are short-lived (`with store.connect() as conn`) — sqlite3
    auto-commits on context-manager exit, rolls back on exception.
  - All timestamps stored as ISO-8601 UTC strings. SQLite has no native
    timestamp type, and ISO strings sort lexically, which is enough for our
    queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AlertRecord:
    id: int
    contract: str
    alerted_at: str
    score: int


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidates_seen (
    contract        TEXT PRIMARY KEY,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    last_score      INTEGER NOT NULL,
    last_snapshot   TEXT  -- JSON blob of the most recent evaluation
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contract        TEXT NOT NULL,
    alerted_at      TEXT NOT NULL,
    score           INTEGER NOT NULL,
    snapshot_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_contract_time
    ON alerts_sent (contract, alerted_at DESC);

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id        INTEGER NOT NULL REFERENCES alerts_sent(id),
    contract        TEXT NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ('approve','skip','snooze')),
    decided_at      TEXT NOT NULL,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_alert ON decisions (alert_id);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     INTEGER NOT NULL REFERENCES decisions(id),
    entry_mcap_usd  REAL,
    exit_mcap_usd   REAL,
    entry_size_sol  REAL,
    exit_size_sol   REAL,
    pnl_sol         REAL,
    opened_at       TEXT,
    closed_at       TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS rugcheck_cache (
    contract        TEXT PRIMARY KEY,
    fetched_at      TEXT NOT NULL,
    result_json     TEXT NOT NULL
);
"""


class StateStore:
    """Thin wrapper around a SQLite file.

    Usage:
        store = StateStore(Path("alert_bot.db"))
        store.init_schema()
        if not store.alerted_within(contract, hours=24):
            alert_id = store.record_alert(contract, score, snapshot)
            ...
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        # PARSE_DECLTYPES isn't needed because we store everything as TEXT/INT/REAL.
        # check_same_thread=False so async-context code can use it; we serialize
        # via short-lived connections rather than sharing state.

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # Fresh connection per call. SQLite is fine with this; the cost is a
        # few ms per call which is negligible at our poll rate.
        conn = sqlite3.connect(
            self._db_path,
            isolation_level=None,  # autocommit; we'll wrap multi-statement
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        # Ensure parent dir exists (db_path may be ./alert_bot.db or a custom path).
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
        log.info("State store schema initialized at %s", self._db_path)

    # --- candidates_seen --------------------------------------------------

    def upsert_candidate_seen(
        self,
        contract: str,
        score: int,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        now = _utcnow_iso()
        payload = json.dumps(snapshot or {}, default=str)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidates_seen (contract, first_seen_at, last_seen_at, last_score, last_snapshot)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(contract) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    last_score = excluded.last_score,
                    last_snapshot = excluded.last_snapshot
                """,
                (contract, now, now, score, payload),
            )

    # --- alerts_sent ------------------------------------------------------

    def alerted_within(self, contract: str, hours: int) -> bool:
        """Was an alert sent for this contract within the last N hours?"""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts_sent WHERE contract = ? AND alerted_at >= ? LIMIT 1",
                (contract, cutoff),
            ).fetchone()
        return row is not None

    def record_alert(
        self,
        contract: str,
        score: int,
        snapshot: dict[str, Any],
    ) -> int:
        """Insert an alert row and return its id (used to tie to decisions)."""
        now = _utcnow_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO alerts_sent (contract, alerted_at, score, snapshot_json) VALUES (?, ?, ?, ?)",
                (contract, now, score, json.dumps(snapshot, default=str)),
            )
            return int(cur.lastrowid or 0)

    def latest_alert_for(self, contract: str) -> AlertRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, contract, alerted_at, score FROM alerts_sent "
                "WHERE contract = ? ORDER BY alerted_at DESC LIMIT 1",
                (contract,),
            ).fetchone()
        if row is None:
            return None
        return AlertRecord(id=row["id"], contract=row["contract"], alerted_at=row["alerted_at"], score=row["score"])

    # --- decisions --------------------------------------------------------

    def record_decision(
        self,
        contract: str,
        decision: str,
        *,
        notes: str | None = None,
    ) -> int | None:
        """Tie a user's button-press to the most recent alert for this contract.

        Returns the new decision id, or None if no alert was found to tie to
        (e.g. callback fired but the alert row was somehow deleted).
        """
        alert = self.latest_alert_for(contract)
        if alert is None:
            log.warning("Decision %r for %s with no matching alert row", decision, contract)
            return None
        now = _utcnow_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO decisions (alert_id, contract, decision, decided_at, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (alert.id, contract, decision, now, notes),
            )
            return int(cur.lastrowid or 0)

    # --- rugcheck cache (cross-session) ----------------------------------

    def cache_rugcheck(self, contract: str, result_json: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rugcheck_cache (contract, fetched_at, result_json)
                VALUES (?, ?, ?)
                ON CONFLICT(contract) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    result_json = excluded.result_json
                """,
                (contract, _utcnow_iso(), result_json),
            )

    def get_cached_rugcheck(self, contract: str, max_age_hours: int = 24) -> str | None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM rugcheck_cache WHERE contract = ? AND fetched_at >= ?",
                (contract, cutoff),
            ).fetchone()
        return row["result_json"] if row else None

    # --- aggregate / health ---------------------------------------------

    def counts(self) -> dict[str, int]:
        """For the daily health ping."""
        with self.connect() as conn:
            cs = conn.execute("SELECT COUNT(*) AS c FROM candidates_seen").fetchone()["c"]
            al = conn.execute("SELECT COUNT(*) AS c FROM alerts_sent").fetchone()["c"]
            dc = conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
            return {"candidates_seen": cs, "alerts_sent": al, "decisions": dc}


if __name__ == "__main__":
    # Smoke test: create the DB, exercise each table, print counts.
    from alert_bot.config import configure_logging, load_runtime_config

    configure_logging("INFO")
    # Use load_runtime_config so we hit the same path the main loop will,
    # but tolerate missing .env by falling back to a local test DB.
    try:
        cfg = load_runtime_config()
        db_path = cfg.db_path
    except RuntimeError:
        db_path = Path("alert_bot.db")
        log.warning(".env missing; using local %s for smoke test", db_path)

    store = StateStore(db_path)
    store.init_schema()
    store.upsert_candidate_seen("TESTCONTRACT", score=3, snapshot={"hello": "world"})
    assert not store.alerted_within("TESTCONTRACT", hours=24)
    alert_id = store.record_alert("TESTCONTRACT", score=4, snapshot={"hello": "world", "score": 4})
    assert store.alerted_within("TESTCONTRACT", hours=24)
    dec_id = store.record_decision("TESTCONTRACT", "skip", notes="smoke test")
    log.info("Inserted alert_id=%s decision_id=%s", alert_id, dec_id)
    log.info("Counts: %s", store.counts())
