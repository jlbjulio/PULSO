
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pulso.clinical.encounters import Encounter, EncounterState
from pulso.clinical.events import ClinicalEvent, Utterance
from pulso.clinical.orders import Order, OrderState, transition
from pulso.storage.audit import append_audit_event, canonical_json
from pulso.storage.database import SQLiteDatabase


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _outbox(connection: sqlite3.Connection, event_type: str, entity_id: str, payload: Any) -> None:
    payload_json = canonical_json(payload)
    payload_hash = hashlib.sha256(f"{event_type}:{entity_id}:{payload_json}".encode()).hexdigest()
    now = utc_iso()
    connection.execute(
        """INSERT OR IGNORE INTO sync_outbox
        (id, event_type, entity_id, payload_json, payload_hash, state, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (str(uuid4()), event_type, entity_id, payload_json, payload_hash, now, now),
    )


class EncounterRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, encounter: Encounter) -> Encounter:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO encounters
                (id, patient_ref, bed, clinician_id, state, critical_mode, language, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    encounter.id,
                    encounter.patient_ref,
                    encounter.bed,
                    encounter.clinician_id,
                    encounter.state.value,
                    int(encounter.critical_mode),
                    encounter.language,
                    encounter.started_at.isoformat(),
                ),
            )
            payload = encounter.model_dump(mode="json")
            append_audit_event(
                connection,
                entity_type="encounter",
                entity_id=encounter.id,
                action="started",
                actor=encounter.clinician_id,
                payload=payload,
            )
            _outbox(connection, "encounter.started", encounter.id, payload)
        return encounter

    def get(self, encounter_id: str) -> Encounter:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM encounters WHERE id = ?", (encounter_id,)
            ).fetchone()
        if not row:
            raise KeyError(encounter_id)
        return Encounter(
            id=row["id"],
            patient_ref=row["patient_ref"],
            bed=row["bed"],
            clinician_id=row["clinician_id"],
            state=row["state"],
            critical_mode=bool(row["critical_mode"]),
            language=row["language"],
            started_at=row["started_at"],
            closed_at=row["closed_at"],
        )

    def set_state(self, encounter_id: str, state: EncounterState, *, actor: str) -> Encounter:
        current = self.get(encounter_id)
        closed_at = datetime.now(UTC) if state == EncounterState.CLOSED else None
        critical = state == EncounterState.CRITICAL
        updated = current.model_copy(
            update={"state": state, "critical_mode": critical, "closed_at": closed_at}
        )
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE encounters SET state=?, critical_mode=?, closed_at=? WHERE id=?",
                (
                    state.value,
                    int(critical),
                    closed_at.isoformat() if closed_at else None,
                    encounter_id,
                ),
            )
            append_audit_event(
                connection,
                entity_type="encounter",
                entity_id=encounter_id,
                action=f"state.{state.value}",
                actor=actor,
                payload=updated.model_dump(mode="json"),
            )
        return updated

    def update_patient_ref(self, encounter_id: str, patient_ref: str, *, actor: str) -> Encounter:
        value = patient_ref.strip()
        if not value:
            raise ValueError("patient reference cannot be empty")
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE encounters SET patient_ref=? WHERE id=?",
                (value, encounter_id),
            )
            connection.execute(
                "UPDATE clinical_events SET patient_ref=? WHERE encounter_id=?",
                (value, encounter_id),
            )
            append_audit_event(
                connection,
                entity_type="encounter",
                entity_id=encounter_id,
                action="patient.identified",
                actor=actor,
                payload={"patient_ref": value},
            )
        return self.get(encounter_id)

    def update_language(self, encounter_id: str, language: str, *, actor: str) -> Encounter:
        value = language.strip().casefold()
        if not value:
            raise ValueError("encounter language cannot be empty")
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE encounters SET language=? WHERE id=?",
                (value, encounter_id),
            )
            append_audit_event(
                connection,
                entity_type="encounter",
                entity_id=encounter_id,
                action="language.updated",
                actor=actor,
                payload={"language": value},
            )
        return self.get(encounter_id)

    def add_utterance(self, encounter_id: str, utterance: Utterance) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO utterances
                (id, encounter_id, speaker, language, original_text, translated_text,
                 started_at_ms, ended_at_ms, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    utterance.id,
                    encounter_id,
                    utterance.speaker.value,
                    utterance.language,
                    utterance.original_text,
                    utterance.translated_text,
                    utterance.started_at_ms,
                    utterance.ended_at_ms,
                    utterance.confidence,
                    utterance.created_at.isoformat(),
                ),
            )

    def save_event(self, event: ClinicalEvent, *, actor: str) -> None:
        payload = event.model_dump(mode="json")
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO clinical_events
                (id, source_event_id, encounter_id, type, state, actor_role, patient_ref,
                 evidence_utterance_ids_json, payload_json, actionable, confirmation_required,
                 missing_fields_json, rag_required, supersedes_event_id, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.source_event_id,
                    event.encounter_id,
                    event.type.value,
                    event.state.value,
                    event.actor_role.value,
                    event.patient_ref,
                    canonical_json(event.evidence_utterance_ids),
                    canonical_json(event.payload),
                    int(event.actionable),
                    int(event.confirmation_required),
                    canonical_json(event.missing_fields),
                    int(event.rag_required),
                    event.supersedes_event_id,
                    event.confidence,
                    event.created_at.isoformat(),
                ),
            )
            append_audit_event(
                connection,
                entity_type="clinical_event",
                entity_id=event.id,
                action="candidate.saved",
                actor=actor,
                payload=payload,
            )

    def list_events(self, encounter_id: str) -> list[ClinicalEvent]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM clinical_events WHERE encounter_id=? ORDER BY created_at",
                (encounter_id,),
            ).fetchall()
        return [
            ClinicalEvent(
                id=row["id"],
                source_event_id=row["source_event_id"],
                encounter_id=row["encounter_id"],
                type=row["type"],
                state=row["state"],
                actor_role=row["actor_role"],
                patient_ref=row["patient_ref"],
                evidence_utterance_ids=json.loads(row["evidence_utterance_ids_json"]),
                payload=json.loads(row["payload_json"]),
                actionable=bool(row["actionable"]),
                confirmation_required=bool(row["confirmation_required"]),
                missing_fields=json.loads(row["missing_fields_json"]),
                rag_required=bool(row["rag_required"]),
                supersedes_event_id=row["supersedes_event_id"],
                confidence=row["confidence"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_rag_check(
        self,
        encounter_id: str,
        *,
        query: str,
        results: list[dict[str, Any]],
        actor: str,
        event_id: str | None = None,
    ) -> str:
        check_id = str(uuid4())
        payload = {"query": query, "results": results, "event_id": event_id}
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO rag_checks
                (id, encounter_id, event_id, query, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (check_id, encounter_id, event_id, query, canonical_json(results), utc_iso()),
            )
            append_audit_event(
                connection,
                entity_type="rag_check",
                entity_id=check_id,
                action="evidence.retrieved",
                actor=actor,
                payload=payload,
            )
        return check_id

    def save_order(self, order: Order, *, actor: str) -> Order:
        payload = order.model_dump(mode="json")
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO orders
                (id, encounter_id, event_id, category, destination, request, state,
                 clinician_id, signature, readback_text, idempotency_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.id,
                    order.encounter_id,
                    order.event_id,
                    order.category,
                    order.destination,
                    order.request,
                    order.state.value,
                    order.clinician_id,
                    order.signature,
                    order.readback_text,
                    order.idempotency_key,
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO order_transitions
                (order_id, state, actor, created_at) VALUES (?, ?, ?, ?)""",
                (order.id, order.state.value, actor, utc_iso()),
            )
            append_audit_event(
                connection,
                entity_type="order",
                entity_id=order.id,
                action="created",
                actor=actor,
                payload=payload,
            )
        return order

    def get_order(self, order_id: str) -> Order:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise KeyError(order_id)
        return Order(**dict(row))

    def transition_order(
        self,
        order_id: str,
        target: OrderState,
        *,
        actor: str,
        note: str | None = None,
        clinician_id: str | None = None,
        signature: str | None = None,
    ) -> Order:
        current = self.get_order(order_id)
        if clinician_id or signature:
            current = current.model_copy(
                update={
                    "clinician_id": clinician_id or current.clinician_id,
                    "signature": signature or current.signature,
                }
            )
        updated = transition(current, target)
        payload = updated.model_dump(mode="json")
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE orders SET state=?, clinician_id=?, signature=?, updated_at=?
                WHERE id=?""",
                (
                    updated.state.value,
                    updated.clinician_id,
                    updated.signature,
                    updated.updated_at.isoformat(),
                    order_id,
                ),
            )
            connection.execute(
                """INSERT INTO order_transitions
                (order_id, previous_state, state, actor, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, current.state.value, target.value, actor, note, utc_iso()),
            )
            append_audit_event(
                connection,
                entity_type="order",
                entity_id=order_id,
                action=f"state.{target.value}",
                actor=actor,
                payload=payload,
            )
            if target == OrderState.CONFIRMED:
                _outbox(connection, "order.confirmed", order_id, payload)
        return updated

    def list_orders(self, encounter_id: str) -> list[Order]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM orders WHERE encounter_id=? ORDER BY updated_at DESC",
                (encounter_id,),
            ).fetchall()
        return [Order(**dict(row)) for row in rows]

    def dashboard(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            active = connection.execute(
                "SELECT COUNT(*) FROM encounters WHERE state!='closed'"
            ).fetchone()[0]
            pending = connection.execute(
                """SELECT COUNT(*) FROM orders
                WHERE state IN ('awaiting_confirmation','confirmed','dispatched')"""
            ).fetchone()[0]
            queued = connection.execute(
                "SELECT COUNT(*) FROM sync_outbox WHERE state='pending'"
            ).fetchone()[0]
        return {"active_encounters": active, "pending_orders": pending, "queued_messages": queued}
