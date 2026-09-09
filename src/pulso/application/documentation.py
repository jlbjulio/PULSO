"""Evidence-grounded clinical documentation assembled without new inference."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pulso.domain.clinical_events import ClinicalEvent, EventType
from pulso.domain.encounters import ClinicalDocument
from pulso.infrastructure.audit.ledger import append_audit_event
from pulso.infrastructure.repositories.encounters import EncounterRepository


def _label(event: ClinicalEvent) -> str:
    payload = ", ".join(f"{key}: {value}" for key, value in event.payload.items())
    return payload or event.type.value


def build_document(encounter_id: str, events: list[ClinicalEvent]) -> ClinicalDocument:
    groups: dict[str, list[str]] = {
        "allergies": [],
        "symptoms": [],
        "findings": [],
        "assessments": [],
        "interventions": [],
        "results": [],
        "pending_orders": [],
    }
    for event in events:
        value = _label(event)
        if event.type == EventType.ALLERGY:
            groups["allergies"].append(value)
        elif event.type in {EventType.SYMPTOM, EventType.PATIENT_REPORT}:
            groups["symptoms"].append(value)
        elif event.type in {EventType.VITAL_SIGN, EventType.EXAM_FINDING}:
            groups["findings"].append(value)
        elif event.type in {EventType.CLINICAL_ASSESSMENT, EventType.DIAGNOSIS}:
            groups["assessments"].append(value)
        elif event.type in {
            EventType.MEDICATION_ADMINISTRATION,
            EventType.PROCEDURE_PERFORMED,
            EventType.CODE_EVENT,
        }:
            groups["interventions"].append(value)
        elif event.type == EventType.RESULT:
            groups["results"].append(value)
        elif event.actionable:
            groups["pending_orders"].append(value)
    summary_parts = [
        f"Síntomas: {'; '.join(groups['symptoms']) or 'sin datos'}.",
        f"Hallazgos: {'; '.join(groups['findings']) or 'sin datos'}.",
        f"Evaluación documentada: {'; '.join(groups['assessments']) or 'sin datos'}.",
    ]
    return ClinicalDocument(encounter_id=encounter_id, summary=" ".join(summary_parts), **groups)


def save_document(
    repository: EncounterRepository,
    document: ClinicalDocument,
    *,
    actor: str,
    signature: str | None = None,
) -> ClinicalDocument:
    now = datetime.now(UTC)
    if signature:
        document = document.model_copy(update={"signed_by": actor, "signed_at": now})
    payload = document.model_dump(mode="json")
    with repository.database.transaction() as connection:
        connection.execute(
            """INSERT INTO clinical_documents
            (encounter_id, document_json, signed_by, signed_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(encounter_id) DO UPDATE SET document_json=excluded.document_json,
            signed_by=excluded.signed_by, signed_at=excluded.signed_at,
            updated_at=excluded.updated_at""",
            (
                document.encounter_id,
                json.dumps(payload, ensure_ascii=False),
                document.signed_by,
                document.signed_at.isoformat() if document.signed_at else None,
                now.isoformat(),
            ),
        )
        append_audit_event(
            connection,
            entity_type="clinical_document",
            entity_id=document.encounter_id,
            action="signed" if signature else "reviewed",
            actor=actor,
            payload=payload,
        )
    return document
