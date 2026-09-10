
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
    "código rosa": "Equipo Obstétrico",
    "codigo rosa": "Equipo Obstétrico",
    "psicología": "Psicología de Urgencias",
    "psicologia": "Psicología de Urgencias",
    "psiquiatría": "Psiquiatría de Urgencias",
    "psiquiatria": "Psiquiatría de Urgencias",
    "trabajo social": "Trabajo Social",
    "cirugía de trauma": "Cirugía de Trauma",
    "cirugia de trauma": "Cirugía de Trauma",
    "cirugía general": "Cirugía General",
    "cirugia general": "Cirugía General",
    "anestesiología": "Anestesiología",
    "anestesiologia": "Anestesiología",
    "cardiología": "Cardiología Intervencionista",
    "cardiologia": "Cardiología Intervencionista",
    "neurocirugía": "Neurocirugía",
    "neurocirugia": "Neurocirugía",
    "ortopedia": "Ortopedia",
    "oftalmología": "Oftalmología",
    "oftalmologia": "Oftalmología",
    "otorrinolaringología": "Otorrinolaringología",
    "otorrinolaringologia": "Otorrinolaringología",
    "pediatría": "Pediatría de Urgencias",
    "pediatria": "Pediatría de Urgencias",
    "terapia respiratoria": "Terapia Respiratoria",
    "farmacia clínica": "Farmacia Clínica de Urgencias",
    "farmacia clinica": "Farmacia Clínica de Urgencias",
    "transfusión masiva": "Banco de Sangre",
    "transfusion masiva": "Banco de Sangre",
    "camillero": "Transporte Crítico",
    "limpieza": "Apoyo Logístico",
    "banco de sangre": "Banco de sangre",
    "rayos x": "Imagenología",
    "radiografía": "Imagenología",
    "tomografía": "Imagenología",
}


def destination_for(event_type: EventType, request: str) -> str:
    if event_type not in {EventType.CONSULT_ORDER, EventType.CODE_EVENT}:
        return ROUTES.get(event_type, "Coordinación de urgencias")
    normalized = request.casefold()
    for phrase in sorted(TEAM_ALIASES, key=len, reverse=True):
        if phrase in normalized:
            return TEAM_ALIASES[phrase]
    return ROUTES.get(event_type, "Coordinación de urgencias")
