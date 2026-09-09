"""Closed-loop order creation and confirmation."""

from __future__ import annotations

import hashlib

from pulso.domain.clinical_events import ORDER_TYPES, ClinicalEvent
from pulso.domain.orders import Order, OrderState
from pulso.infrastructure.repositories.encounters import EncounterRepository
from pulso.infrastructure.routing.dispatcher import destination_for


def _request_text(event: ClinicalEvent) -> str:
    return str(
        event.payload.get("explicit_command")
        or event.payload.get("request")
        or event.payload.get("name")
        or event.type.value
    )


class OrderService:
    def __init__(self, repository: EncounterRepository) -> None:
        self.repository = repository

    def draft_from_event(self, event: ClinicalEvent, *, actor: str) -> Order:
        if event.type not in ORDER_TYPES or not event.actionable:
            raise ValueError("only explicit actionable order events can create drafts")
        request = _request_text(event)
        digest = hashlib.sha256(
            f"{event.encounter_id}:{','.join(sorted(event.evidence_utterance_ids))}:{request}".encode()
        ).hexdigest()
        order = Order(
            encounter_id=event.encounter_id,
            event_id=event.id,
            category=event.type.value,
            destination=destination_for(event.type, request),
            request=request,
            state=OrderState.AWAITING_CONFIRMATION,
            readback_text=f"Confirmar envío a {destination_for(event.type, request)}: {request}",
            idempotency_key=digest,
        )
        return self.repository.save_order(order, actor=actor)

    def confirm(self, order_id: str, *, clinician_id: str, signature: str) -> Order:
        if not signature.strip():
            raise ValueError("a local clinician signature is required")
        return self.repository.transition_order(
            order_id,
            OrderState.CONFIRMED,
            actor=clinician_id,
            clinician_id=clinician_id,
            signature=signature,
            note="closed-loop readback confirmed",
        )

    def dispatch(self, order_id: str, *, actor: str = "pulso.local") -> Order:
        return self.repository.transition_order(order_id, OrderState.DISPATCHED, actor=actor)

    def acknowledge(self, order_id: str, *, actor: str) -> Order:
        return self.repository.transition_order(order_id, OrderState.ACCEPTED, actor=actor)

    def cancel(self, order_id: str, *, actor: str, reason: str) -> Order:
        return self.repository.transition_order(
            order_id, OrderState.CANCELLED, actor=actor, note=reason
        )
