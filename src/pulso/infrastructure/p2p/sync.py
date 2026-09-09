"""Offline outbox semantics for an authorized Pear/P2P transport."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from pulso.infrastructure.database.sqlite import SQLiteDatabase


class PeerTransport(Protocol):
    def send(self, event_type: str, entity_id: str, payload_json: str) -> None: ...


class OutboxSync:
    def __init__(self, database: SQLiteDatabase, transport: PeerTransport) -> None:
        self.database = database
        self.transport = transport

    def flush(self, limit: int = 20) -> dict[str, int]:
        counts = {"sent": 0, "failed": 0}
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM sync_outbox
                WHERE state='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                ORDER BY created_at LIMIT ?""",
                (datetime.now(UTC).isoformat(), limit),
            ).fetchall()
        for row in rows:
            try:
                self.transport.send(row["event_type"], row["entity_id"], row["payload_json"])
                with self.database.transaction() as connection:
                    connection.execute(
                        "UPDATE sync_outbox SET state='sent', updated_at=? WHERE id=?",
                        (datetime.now(UTC).isoformat(), row["id"]),
                    )
                counts["sent"] += 1
            except Exception as error:
                attempts = int(row["attempts"]) + 1
                delay = min(2**attempts, 300)
                with self.database.transaction() as connection:
                    connection.execute(
                        """UPDATE sync_outbox SET attempts=?, next_attempt_at=?,
                        last_error=?, updated_at=?
                        WHERE id=?""",
                        (
                            attempts,
                            (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(),
                            str(error),
                            datetime.now(UTC).isoformat(),
                            row["id"],
                        ),
                    )
                counts["failed"] += 1
        return counts
