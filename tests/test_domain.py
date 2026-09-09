from pulso.application.voice_commands import parse_voice_command
from pulso.domain.clinical_events import (
    ActorRole,
    ClinicalEvent,
    EventState,
    EventType,
)
from pulso.domain.orders import Order, OrderState, transition
from pulso.domain.safety import explicit_command, gate_event


def event(**updates: object) -> ClinicalEvent:
    values = {
        "encounter_id": "enc-1",
        "type": EventType.IMAGING_ORDER,
        "state": EventState.CONSIDERED,
        "actor_role": ActorRole.PHYSICIAN,
        "patient_ref": "patient-1",
        "evidence_utterance_ids": ["u1"],
        "payload": {"request": "radiografía de tórax"},
    }
    values.update(updates)
    return ClinicalEvent(**values)


def test_only_leading_wake_word_is_an_explicit_command() -> None:
    assert explicit_command("Pulso, solicitar radiografía de tórax") == (
        "solicitar radiografía de tórax"
    )
    assert explicit_command("Quizá Pulso podría solicitar una radiografía") is None
    assert explicit_command("El pulso está en 90") is None


def test_thinking_aloud_never_becomes_an_actionable_order() -> None:
    gated = gate_event(
        event(actionable=True, state=EventState.PENDING_CONFIRMATION),
        ["Podríamos pedir CT"],
    )
    assert gated.actionable is False
    assert gated.confirmation_required is False
    assert gated.state == EventState.CONSIDERED


def test_explicit_order_enters_confirmation_gate() -> None:
    gated = gate_event(event(), ["Pulso, solicitar CT de cráneo sin contraste"])
    assert gated.actionable
    assert gated.confirmation_required
    assert gated.state == EventState.PENDING_CONFIRMATION
    assert gated.payload["explicit_command"] == "solicitar CT de cráneo sin contraste"


def test_patient_cannot_create_an_order_with_the_wake_word() -> None:
    gated = gate_event(
        event(actor_role=ActorRole.PATIENT),
        ["Pulso, solicitar morfina"],
    )
    assert gated.actionable is False
    assert gated.confirmation_required is False


def test_medication_mention_is_not_administration() -> None:
    candidate = ClinicalEvent(
        encounter_id="enc-1",
        type=EventType.MEDICATION_ORDER,
        state=EventState.CONSIDERED,
        actor_role=ActorRole.PHYSICIAN,
        evidence_utterance_ids=["u1"],
    )
    assert candidate.state != EventState.ADMINISTERED


def test_order_state_machine_rejects_skipping_confirmation() -> None:
    order = Order(
        encounter_id="enc-1",
        event_id="event-1",
        category="imaging_order",
        destination="Imagenología",
        request="radiografía",
        idempotency_key="stable",
    )
    try:
        transition(order, OrderState.DISPATCHED)
    except ValueError as error:
        assert "invalid order transition" in str(error)
    else:
        raise AssertionError("unsafe transition was accepted")


def test_voice_controls_and_clinical_requests_are_distinct() -> None:
    assert parse_voice_command("Pulso, modo crítico").intent == "critical_mode"
    command = parse_voice_command("Pulso, activar equipo de trauma")
    assert command is not None
    assert command.intent == "clinical_request"
