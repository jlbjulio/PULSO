"""Deterministic safety gates around model output."""

from __future__ import annotations

import re

from .events import ORDER_TYPES, ActorRole, ClinicalEvent, EventState

WAKE_WORD = re.compile(r"^\s*pulso\s*[,;:]?\s+", re.IGNORECASE)
AUTHORIZED_ORDER_ROLES = {ActorRole.PHYSICIAN, ActorRole.NURSE, ActorRole.PARAMEDIC}


def explicit_command(text: str) -> str | None:
    """Return the command only when the utterance starts with the wake word."""

    match = WAKE_WORD.match(text)
    if not match:
        return None
    command = text[match.end() :].strip()
    return command or None


def gate_event(event: ClinicalEvent, evidence_texts: list[str]) -> ClinicalEvent:
    """Make unsupported model actions non-actionable before persistence."""

    if event.type not in ORDER_TYPES:
        return event
    command = next(
        (explicit_command(text) for text in evidence_texts if explicit_command(text)), None
    )
    if not command or event.actor_role not in AUTHORIZED_ORDER_ROLES:
        safe_state = (
            EventState.CONSIDERED if event.state == EventState.PENDING_CONFIRMATION else event.state
        )
        return event.model_copy(
            update={
                "actionable": False,
                "confirmation_required": False,
                "state": safe_state,
            }
        )
    return event.model_copy(
        update={
            "actionable": True,
            "confirmation_required": True,
            "state": EventState.PENDING_CONFIRMATION,
            "payload": {**event.payload, "explicit_command": command},
        }
    )
