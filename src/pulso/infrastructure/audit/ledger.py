"""Tamper-evident local audit chain."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_audit_event(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    payload: dict[str, Any],
) -> str:
    previous = connection.execute(
        "SELECT event_hash FROM audit_events ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    previous_hash = str(previous["event_hash"]) if previous else None
    created_at = datetime.now(UTC).isoformat()
    body = canonical_json(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "actor": actor,
            "payload": payload,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
    )
    event_hash = hashlib.sha256(body.encode()).hexdigest()
    connection.execute(
        """INSERT INTO audit_events
        (id, entity_type, entity_id, action, actor, payload_json,
         previous_hash, event_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(uuid4()),
            entity_type,
            entity_id,
            action,
            actor,
            canonical_json(payload),
            previous_hash,
            event_hash,
            created_at,
        ),
    )
    return event_hash


def verify_audit_chain(connection: sqlite3.Connection) -> bool:
    previous_hash: str | None = None
    rows = connection.execute("SELECT * FROM audit_events ORDER BY rowid").fetchall()
    for row in rows:
        if row["previous_hash"] != previous_hash:
            return False
        body = canonical_json(
            {
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "action": row["action"],
                "actor": row["actor"],
                "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"],
                "created_at": row["created_at"],
            }
        )
        if hashlib.sha256(body.encode()).hexdigest() != row["event_hash"]:
            return False
        previous_hash = row["event_hash"]
    return True
