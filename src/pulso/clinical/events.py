
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventType(StrEnum):
    PATIENT_REPORT = "patient_report"
    SYMPTOM = "symptom"
    ALLERGY = "allergy"
    MEDICATION_HISTORY = "medication_history"
    VITAL_SIGN = "vital_sign"
    EXAM_FINDING = "exam_finding"
    CLINICAL_ASSESSMENT = "clinical_assessment"
    DIAGNOSIS = "diagnosis"
    MEDICATION_ORDER = "medication_order"
    MEDICATION_ADMINISTRATION = "medication_administration"
    PROCEDURE_ORDER = "procedure_order"
    PROCEDURE_PERFORMED = "procedure_performed"
    LAB_ORDER = "lab_order"
    IMAGING_ORDER = "imaging_order"
    CONSULT_ORDER = "consult_order"
    RESULT = "result"
    CODE_EVENT = "code_event"
    TRANSFER = "transfer"
    DISPOSITION = "disposition"
    HANDOFF = "handoff"


class EventState(StrEnum):
    REPORTED = "reported"
    OBSERVED = "observed"
    CONSIDERED = "considered"
    PLANNED = "planned"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    ADMINISTERED = "administered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DENIED = "denied"
    UNKNOWN = "unknown"


class ActorRole(StrEnum):
    PATIENT = "patient"
    PHYSICIAN = "physician"
    NURSE = "nurse"
    PARAMEDIC = "paramedic"
    FAMILY = "family"
    SYSTEM = "system"
    UNKNOWN = "unknown"


ORDER_TYPES = {
    EventType.MEDICATION_ORDER,
    EventType.PROCEDURE_ORDER,
    EventType.LAB_ORDER,
    EventType.IMAGING_ORDER,
    EventType.CONSULT_ORDER,
    EventType.TRANSFER,
    EventType.CODE_EVENT,
}


class Utterance(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    speaker: ActorRole = ActorRole.UNKNOWN
    language: str = "es"
    original_text: str = Field(min_length=1)
    translated_text: str | None = None
    started_at_ms: int | None = Field(default=None, ge=0)
    ended_at_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("original_text", "translated_text", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class ClinicalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_event_id: str | None = None
    encounter_id: str
    type: EventType
    state: EventState
    actor_role: ActorRole
    patient_ref: str | None = None
    evidence_utterance_ids: list[str] = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    actionable: bool = False
    confirmation_required: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    rag_required: bool = False
    supersedes_event_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def enforce_safety_invariants(self) -> ClinicalEvent:
        if self.type in ORDER_TYPES and self.actionable:
            self.confirmation_required = True
            if self.state not in {
                EventState.PENDING_CONFIRMATION,
                EventState.CONFIRMED,
                EventState.CANCELLED,
                EventState.DENIED,
            }:
                raise ValueError("actionable orders must enter the closed-loop workflow")
        if (
            self.state == EventState.ADMINISTERED
            and self.type != EventType.MEDICATION_ADMINISTRATION
        ):
            raise ValueError("administered is only valid for medication administration evidence")
        return self


class ExtractionResult(BaseModel):
    events: list[ClinicalEvent] = Field(default_factory=list)
    ignored_utterance_ids: list[str] = Field(default_factory=list)
    session_flags: list[str] = Field(default_factory=list)
