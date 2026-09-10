"""Closed-loop orders, routing, acknowledgement, and replacement rules."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class OrderState(StrEnum):
    CONSIDERED = "considered"
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.CONSIDERED: {OrderState.DRAFT, OrderState.CANCELLED},
    OrderState.DRAFT: {OrderState.AWAITING_CONFIRMATION, OrderState.CANCELLED},
    OrderState.AWAITING_CONFIRMATION: {OrderState.CONFIRMED, OrderState.CANCELLED},
    OrderState.CONFIRMED: {OrderState.DISPATCHED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.DISPATCHED: {OrderState.ACCEPTED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.ACCEPTED: {OrderState.IN_PROGRESS, OrderState.COMPLETED, OrderState.CANCELLED},
    OrderState.IN_PROGRESS: {OrderState.COMPLETED, OrderState.CANCELLED},
    OrderState.FAILED: {OrderState.DISPATCHED, OrderState.CANCELLED},
    OrderState.COMPLETED: set(),
    OrderState.CANCELLED: set(),
}


class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    encounter_id: str
    event_id: str
    category: str
    destination: str
    request: str = Field(min_length=1)
    state: OrderState = OrderState.DRAFT
    clinician_id: str | None = None
    signature: str | None = None
    readback_text: str | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def signed_when_confirmed(self) -> Order:
        signed_states = {
            OrderState.CONFIRMED,
            OrderState.DISPATCHED,
            OrderState.ACCEPTED,
            OrderState.IN_PROGRESS,
            OrderState.COMPLETED,
            OrderState.FAILED,
        }
        if self.state in signed_states and not (self.clinician_id and self.signature):
            raise ValueError("confirmed orders require clinician identity and signature")
        return self


def transition(order: Order, target: OrderState) -> Order:
    if target not in ALLOWED_TRANSITIONS[order.state]:
        raise ValueError(f"invalid order transition: {order.state} -> {target}")
    return order.model_copy(update={"state": target, "updated_at": utc_now()})
