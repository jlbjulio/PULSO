"""Hands-free command interpretation outside the generative model."""

from __future__ import annotations

from dataclasses import dataclass

from pulso.domain.safety import explicit_command


@dataclass(frozen=True)
class VoiceCommand:
    intent: str
    payload: str


CONTROL_COMMANDS = {
    "iniciar captura": "start_capture",
    "pausar captura": "pause_capture",
    "reanudar captura": "resume_capture",
    "modo crítico": "critical_mode",
    "modo critico": "critical_mode",
    "finalizar atención": "finish_encounter",
    "finalizar atencion": "finish_encounter",
    "cancelar orden": "cancel_order",
    "confirmar orden": "confirm_order",
}


def parse_voice_command(text: str) -> VoiceCommand | None:
    command = explicit_command(text)
    if not command:
        return None
    normalized = command.casefold().strip(" .")
    for phrase, intent in CONTROL_COMMANDS.items():
        if normalized.startswith(phrase):
            return VoiceCommand(intent=intent, payload=command[len(phrase) :].strip(" ,:"))
    return VoiceCommand(intent="clinical_request", payload=command)
