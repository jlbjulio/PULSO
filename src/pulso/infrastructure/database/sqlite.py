"""SQLite persistence for an offline-first emergency workflow."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = PROJECT_ROOT / "runtime-data" / "pulso.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS encounters (
    id TEXT PRIMARY KEY,
    patient_ref TEXT NOT NULL,
    bed TEXT NOT NULL,
    clinician_id TEXT NOT NULL,
    state TEXT NOT NULL,
    critical_mode INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'es',
    started_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_bed
ON encounters(bed) WHERE state != 'closed';

CREATE TABLE IF NOT EXISTS utterances (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    speaker TEXT NOT NULL,
    language TEXT NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT,
    started_at_ms INTEGER,
    ended_at_ms INTEGER,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clinical_events (
    id TEXT PRIMARY KEY,
    source_event_id TEXT,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    type TEXT NOT NULL,
    state TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    patient_ref TEXT,
    evidence_utterance_ids_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    actionable INTEGER NOT NULL,
    confirmation_required INTEGER NOT NULL,
    missing_fields_json TEXT NOT NULL,
    rag_required INTEGER NOT NULL,
    supersedes_event_id TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    event_id TEXT NOT NULL REFERENCES clinical_events(id),
    category TEXT NOT NULL,
    destination TEXT NOT NULL,
    request TEXT NOT NULL,
    state TEXT NOT NULL,
    clinician_id TEXT,
    signature TEXT,
    readback_text TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    replaces_order_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL REFERENCES orders(id),
    previous_state TEXT,
    state TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_documents (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    local_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    ocr_blocks_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_checks (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    event_id TEXT,
    query TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clinical_documents (
    encounter_id TEXT PRIMARY KEY REFERENCES encounters(id),
    document_json TEXT NOT NULL,
    signed_by TEXT,
    signed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_outbox (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_encounter ON clinical_events(encounter_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_encounter ON orders(encounter_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_outbox_state ON sync_outbox(state, next_attempt_at);
"""


class SQLiteDatabase:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
