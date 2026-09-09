"""Deterministic FHIR R4 export of reviewed local evidence and orders."""

from __future__ import annotations

import re
from typing import Any

from pulso.domain.clinical_events import ClinicalEvent, EventType
from pulso.domain.encounters import Encounter
from pulso.domain.orders import Order, OrderState


def _reference(resource_type: str, identifier: str) -> dict[str, str]:
    return {"reference": f"{resource_type}/{identifier}"}


def _fhir_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\-.]", "-", value).strip("-")
    return (cleaned or "unknown")[:64]


def _text(event: ClinicalEvent) -> str:
    return ", ".join(f"{key}: {value}" for key, value in event.payload.items()) or event.type.value


def _status(event: ClinicalEvent) -> str:
    if event.state.value in {"cancelled", "denied"}:
        return "entered-in-error"
    if event.state.value in {"completed", "administered"}:
        return "final"
    return "preliminary"


def _event_resource(event: ClinicalEvent, patient_id: str, encounter_id: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "id": event.id,
        "subject": _reference("Patient", patient_id),
        "encounter": _reference("Encounter", encounter_id),
        "note": [{"text": _text(event)}],
        "meta": {
            "tag": [
                {"system": "https://pulso.local/event-state", "code": event.state.value},
                {
                    "system": "https://pulso.local/actionable",
                    "code": str(event.actionable).lower(),
                },
            ]
        },
    }
    if event.type == EventType.ALLERGY:
        return {
            "resourceType": "AllergyIntolerance",
            **common,
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active",
                    }
                ]
            },
            "code": {"text": _text(event)},
        }
    if event.type in {EventType.DIAGNOSIS, EventType.CLINICAL_ASSESSMENT}:
        return {
            "resourceType": "Condition",
            **common,
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }
                ]
            },
            "code": {"text": _text(event)},
        }
    if event.type == EventType.MEDICATION_ADMINISTRATION:
        return {
            "resourceType": "MedicationAdministration",
            **common,
            "status": "completed" if event.state.value == "administered" else "unknown",
            "medicationCodeableConcept": {"text": _text(event)},
        }
    if event.type == EventType.PROCEDURE_PERFORMED:
        return {
            "resourceType": "Procedure",
            **common,
            "status": "completed",
            "code": {"text": _text(event)},
        }
    return {
        "resourceType": "Observation",
        **common,
        "status": _status(event),
        "code": {"text": event.type.value.replace("_", " ")},
        "valueString": _text(event),
    }


def _order_resource(
    order: Order, patient_id: str, encounter_id: str, practitioner_id: str
) -> dict[str, Any]:
    status = {
        OrderState.CANCELLED: "revoked",
        OrderState.COMPLETED: "completed",
        OrderState.FAILED: "entered-in-error",
        OrderState.AWAITING_CONFIRMATION: "draft",
    }.get(order.state, "active")
    return {
        "resourceType": "ServiceRequest",
        "id": order.id,
        "status": status,
        "intent": "order",
        "code": {"text": order.request},
        "subject": _reference("Patient", patient_id),
        "encounter": _reference("Encounter", encounter_id),
        "requester": _reference("Practitioner", practitioner_id),
        "performerType": {"text": order.destination},
        "identifier": [
            {"system": "https://pulso.local/idempotency", "value": order.idempotency_key}
        ],
    }


def export_bundle(
    encounter: Encounter,
    events: list[ClinicalEvent],
    orders: list[Order],
) -> dict[str, Any]:
    """Build a local FHIR Bundle without inventing terminology or clinical fields."""
    patient_id = _fhir_id(encounter.patient_ref)
    practitioner_id = _fhir_id(encounter.clinician_id)
    resources: list[dict[str, Any]] = [
        {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [{"system": "https://pulso.local/patient-ref", "value": patient_id}],
        },
        {
            "resourceType": "Practitioner",
            "id": practitioner_id,
            "identifier": [
                {
                    "system": "https://pulso.local/clinician-id",
                    "value": encounter.clinician_id,
                }
            ],
        },
        {
            "resourceType": "Encounter",
            "id": encounter.id,
            "status": "finished" if encounter.closed_at else "in-progress",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "EMER",
            },
            "subject": _reference("Patient", patient_id),
            "participant": [
                {"individual": _reference("Practitioner", practitioner_id)}
            ],
            "location": [{"location": {"display": encounter.bed}}],
            "period": {
                "start": encounter.started_at.isoformat(),
                **({"end": encounter.closed_at.isoformat()} if encounter.closed_at else {}),
            },
        },
    ]
    resources.extend(_event_resource(event, patient_id, encounter.id) for event in events)
    resources.extend(
        _order_resource(order, patient_id, encounter.id, practitioner_id) for order in orders
    )
    resources.extend(
        {
            "resourceType": "Provenance",
            "id": f"provenance-{event.id}",
            "recorded": event.created_at.isoformat(),
            "target": [
                _reference(
                    _event_resource(event, patient_id, encounter.id)["resourceType"],
                    event.id,
                )
            ],
            "agent": [
                {
                    "who": _reference("Practitioner", practitioner_id),
                    "type": {"text": "human-reviewed local extraction"},
                }
            ],
            "entity": [
                {
                    "role": "source",
                    "what": {
                        "identifier": {
                            "system": "https://pulso.local/utterance",
                            "value": utterance_id,
                        }
                    },
                }
                for utterance_id in event.evidence_utterance_ids
            ],
        }
        for event in events
    )
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": encounter.started_at.isoformat(),
        "entry": [{"resource": resource} for resource in resources],
    }
