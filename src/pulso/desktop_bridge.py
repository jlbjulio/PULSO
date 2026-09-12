from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pulso.ai.runtime import QvacRuntime
from pulso.ai.speech import SpeechOutputService
from pulso.clinical.documentation import build_document, export_word_report, save_document
from pulso.clinical.encounter_service import EncounterService
from pulso.clinical.events import ORDER_TYPES, ActorRole
from pulso.clinical.fhir import export_bundle
from pulso.clinical.order_service import OrderService
from pulso.clinical.orders import OrderState
from pulso.storage.database import PROJECT_ROOT, SQLiteDatabase
from pulso.storage.repository import EncounterRepository


def database_for(demo: bool) -> SQLiteDatabase:
    name = "pulso-demo.db" if demo else "pulso.db"
    database = SQLiteDatabase(PROJECT_ROOT / "runtime-data" / name)
    database.initialize()
    return database


def rows(
    database: SQLiteDatabase, query: str, values: tuple[object, ...] = ()
) -> list[dict[str, Any]]:
    with database.connect() as connection:
        return [dict(item) for item in connection.execute(query, values).fetchall()]


def snapshot(repository: EncounterRepository, encounter_id: str) -> dict[str, Any]:
    encounter = repository.get(encounter_id)
    utterances = rows(
        repository.database,
        "SELECT * FROM utterances WHERE encounter_id=? ORDER BY created_at",
        (encounter_id,),
    )
    transitions = rows(
        repository.database,
        """SELECT transition.* FROM order_transitions transition
        JOIN orders ON orders.id=transition.order_id
        WHERE orders.encounter_id=? ORDER BY transition.created_at""",
        (encounter_id,),
    )
    return {
        "encounter": encounter.model_dump(mode="json"),
        "utterances": utterances,
        "events": [item.model_dump(mode="json") for item in repository.list_events(encounter_id)],
        "orders": [item.model_dump(mode="json") for item in repository.list_orders(encounter_id)],
        "transitions": transitions,
        "dashboard": repository.dashboard(),
    }


def reset_demo(database: SQLiteDatabase) -> dict[str, bool]:
    tables = [
        "order_transitions",
        "rag_checks",
        "clinical_documents",
        "sync_outbox",
        "audit_events",
        "orders",
        "clinical_events",
        "utterances",
        "encounters",
    ]
    with database.transaction() as connection:
        for table in tables:
            connection.execute(f"DELETE FROM {table}")
    return {"reset": True}


def process(request: dict[str, Any]) -> Any:
    action = str(request.get("action", ""))
    demo = bool(request.get("demo", False))
    database = database_for(demo)
    repository = EncounterRepository(database)
    encounters = EncounterService(repository)
    orders = OrderService(repository)
    encounter_id = str(request.get("encounter_id", ""))

    if action == "initialize":
        if request.get("warmup"):
            QvacRuntime().warmup()
        return {"ready": True, "demo": demo, "dashboard": repository.dashboard()}
    if action == "reset_demo":
        return reset_demo(database)
    if action == "start":
        patient_ref = str(request.get("patient_ref", "")).strip()
        if not patient_ref:
            prefix = "DEMO" if demo else "URG"
            patient_ref = f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        encounter = encounters.start(
            patient_ref=patient_ref,
            bed=str(request["bed"]),
            clinician_id=str(request["clinician_id"]),
            language=str(request.get("language", "es")),
        )
        return snapshot(repository, encounter.id)
    if action == "snapshot":
        return snapshot(repository, encounter_id)
    if action == "identify_patient":
        repository.update_patient_ref(
            encounter_id,
            str(request["patient_ref"]),
            actor=str(request["actor"]),
        )
        return snapshot(repository, encounter_id)
    if action in {"capture_text", "capture_audio"}:
        if action == "capture_text":
            text = str(request["text"])
            events = encounters.capture_text(
                encounter_id,
                text,
                speaker=ActorRole(str(request.get("speaker", "unknown"))),
                language=str(request.get("language", "auto")),
            )
        else:
            events = encounters.capture_audio(encounter_id, str(request["audio_path"]))
        for event in events:
            if event.type in ORDER_TYPES and event.actionable:
                try:
                    orders.draft_from_event(
                        event, actor=str(request.get("actor", "local.clinician"))
                    )
                except Exception as error:
                    if "UNIQUE constraint" not in str(error):
                        raise
        return snapshot(repository, encounter_id)
    if action == "order_confirm_dispatch":
        order_id = str(request["order_id"])
        actor = str(request["actor"])
        orders.confirm(order_id, clinician_id=actor, signature=str(request["signature"]))
        orders.dispatch(order_id, actor="pulso.local")
        return snapshot(repository, encounter_id)
    if action == "order_cancel":
        orders.cancel(
            str(request["order_id"]),
            actor=str(request["actor"]),
            reason=str(request.get("reason", "Cancelled by clinician")),
        )
        return snapshot(repository, encounter_id)
    if action == "simulate_step":
        order = repository.get_order(str(request["order_id"]))
        actor = f"demo.{order.destination.casefold().replace(' ', '_')}"
        if order.state == OrderState.DISPATCHED:
            orders.acknowledge(order.id, actor=actor)
        elif order.state == OrderState.ACCEPTED:
            orders.begin(order.id, actor=actor)
        elif order.state == OrderState.IN_PROGRESS:
            orders.complete(order.id, actor=actor)
        return snapshot(repository, encounter_id)
    if action == "speak":
        output = PROJECT_ROOT / "runtime-data" / "speech" / f"{uuid4()}.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        SpeechOutputService().synthesize(
            str(request["text"]), output, language=str(request.get("language", "es"))
        )
        return {"output": str(output)}
    if action == "close":
        actor = str(request["actor"])
        signature = str(request["signature"])
        encounters.begin_review(encounter_id, actor=actor)
        document = build_document(encounter_id, repository.list_events(encounter_id))
        document = save_document(repository, document, actor=actor, signature=signature)
        closed = encounters.close(encounter_id, actor=actor)
        events = repository.list_events(encounter_id)
        current_orders = repository.list_orders(encounter_id)
        bundle = export_bundle(
            closed,
            events,
            current_orders,
        )
        export_directory = PROJECT_ROOT / "runtime-data" / "exports"
        fhir_output = export_directory / f"{encounter_id}.fhir.json"
        report_output = export_directory / f"{encounter_id}.docx"
        export_directory.mkdir(parents=True, exist_ok=True)
        fhir_output.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        export_word_report(closed, document, events, current_orders, report_output)
        return {
            "snapshot": snapshot(repository, encounter_id),
            "report_path": str(report_output),
            "fhir_path": str(fhir_output),
        }
    if action == "health":
        return QvacRuntime().health()
    raise ValueError(f"unknown desktop action: {action}")


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = {"ok": True, "data": process(request)}
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
