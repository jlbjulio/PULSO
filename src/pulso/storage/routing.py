
from __future__ import annotations

from pulso.clinical.events import EventType

ROUTES = {
    EventType.IMAGING_ORDER: "Imagenología",
    EventType.LAB_ORDER: "Laboratorio",
    EventType.MEDICATION_ORDER: "Farmacia",
    EventType.PROCEDURE_ORDER: "Procedimientos",
    EventType.CONSULT_ORDER: "Interconsulta",
    EventType.TRANSFER: "Transporte clínico",
    EventType.CODE_EVENT: "Coordinación de urgencias",
}

TEAM_ALIASES = {
    "código azul": "Equipo Código Azul",
    "codigo azul": "Equipo Código Azul",
    "trauma": "Equipo de Trauma",
    "ictus": "Equipo Código Ictus",
    "sepsis": "Equipo de Sepsis",
    "ecmo": "Equipo ECMO",
    "obstétrico": "Equipo Obstétrico",
    "obstetrico": "Equipo Obstétrico",
    "banco de sangre": "Banco de sangre",
    "rayos x": "Imagenología",
    "radiografía": "Imagenología",
    "tomografía": "Imagenología",
}


def destination_for(event_type: EventType, request: str) -> str:
    normalized = request.casefold()
    for phrase, destination in TEAM_ALIASES.items():
        if phrase in normalized:
            return destination
    return ROUTES.get(event_type, "Coordinación de urgencias")
