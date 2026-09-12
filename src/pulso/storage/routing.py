from __future__ import annotations

from pulso.clinical.events import EventType

ROUTES = {
    EventType.IMAGING_ORDER: "Imaging",
    EventType.LAB_ORDER: "Laboratory",
    EventType.MEDICATION_ORDER: "Pharmacy",
    EventType.PROCEDURE_ORDER: "Procedures",
    EventType.CONSULT_ORDER: "Consultation",
    EventType.TRANSFER: "Clinical Transport",
    EventType.CODE_EVENT: "Emergency Coordination",
}

TEAM_ALIASES = {
    "código azul": "Code Blue Team",
    "codigo azul": "Code Blue Team",
    "trauma": "Trauma Team",
    "ictus": "Stroke Team",
    "sepsis": "Sepsis Team",
    "ecmo": "ECMO Team",
    "obstétrico": "Obstetric Team",
    "obstetrico": "Obstetric Team",
    "código rosa": "Obstetric Team",
    "codigo rosa": "Obstetric Team",
    "psicología": "Emergency Psychology",
    "psicologia": "Emergency Psychology",
    "psiquiatría": "Emergency Psychiatry",
    "psiquiatria": "Emergency Psychiatry",
    "trabajo social": "Social Work",
    "cirugía de trauma": "Trauma Surgery",
    "cirugia de trauma": "Trauma Surgery",
    "cirugía general": "General Surgery",
    "cirugia general": "General Surgery",
    "anestesiología": "Anesthesiology",
    "anestesiologia": "Anesthesiology",
    "cardiología": "Interventional Cardiology",
    "cardiologia": "Interventional Cardiology",
    "neurocirugía": "Neurosurgery",
    "neurocirugia": "Neurosurgery",
    "ortopedia": "Orthopedics",
    "oftalmología": "Ophthalmology",
    "oftalmologia": "Ophthalmology",
    "otorrinolaringología": "Otolaryngology",
    "otorrinolaringologia": "Otolaryngology",
    "pediatría": "Emergency Pediatrics",
    "pediatria": "Emergency Pediatrics",
    "terapia respiratoria": "Respiratory Therapy",
    "farmacia clínica": "Emergency Clinical Pharmacy",
    "farmacia clinica": "Emergency Clinical Pharmacy",
    "transfusión masiva": "Blood Bank",
    "transfusion masiva": "Blood Bank",
    "camillero": "Critical Transport",
    "limpieza": "Logistics Support",
    "banco de sangre": "Blood Bank",
    "rayos x": "Imaging",
    "radiografía": "Imaging",
    "tomografía": "Imaging",
}


def destination_for(event_type: EventType, request: str) -> str:
    if event_type not in {EventType.CONSULT_ORDER, EventType.CODE_EVENT}:
        return ROUTES.get(event_type, "Emergency Coordination")
    normalized = request.casefold()
    for phrase in sorted(TEAM_ALIASES, key=len, reverse=True):
        if phrase in normalized:
            return TEAM_ALIASES[phrase]
    return ROUTES.get(event_type, "Emergency Coordination")
