"""Emergency encounter identity and lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class EncounterState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CRITICAL = "critical"
    REVIEW = "review"
    CLOSED = "closed"


class Encounter(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    patient_ref: str = Field(min_length=1)
    bed: str = Field(min_length=1)
    clinician_id: str = Field(min_length=1)
    state: EncounterState = EncounterState.ACTIVE
    started_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None
    critical_mode: bool = False
    language: str = "es"


class ClinicalDocument(BaseModel):
    encounter_id: str
    summary: str
    allergies: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    assessments: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    pending_orders: list[str] = Field(default_factory=list)
    signed_by: str | None = None
    signed_at: datetime | None = None
