
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pulso.ai.rag import RetrievalService
from pulso.ai.runtime import QvacRuntime
from pulso.clinical.documentation import build_document, save_document
from pulso.clinical.encounter_service import EncounterService
from pulso.clinical.events import ActorRole
from pulso.clinical.fhir import export_bundle
from pulso.clinical.order_service import OrderService
from pulso.storage.database import SQLiteDatabase
from pulso.storage.repository import EncounterRepository


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulso", description="PULSO local clinical operations")
    parser.add_argument(
        "command",
        choices=[
            "init",
            "start",
            "capture",
            "critical",
            "review",
            "document",
            "order-confirm",
            "order-dispatch",
            "order-ack",
            "order-start",
            "order-complete",
            "order-cancel",
            "dashboard",
            "rag-index",
            "rag-search",
            "qvac-health",
            "fhir-export",
        ],
    )
    parser.add_argument("--database")
    parser.add_argument("--encounter")
    parser.add_argument("--patient")
    parser.add_argument("--bed")
    parser.add_argument("--clinician", default="demo.clinician")
    parser.add_argument(
        "--speaker", default="physician", choices=[item.value for item in ActorRole]
    )
    parser.add_argument("--language", default="es")
    parser.add_argument("--text")
    parser.add_argument("--order")
    parser.add_argument("--signature")
    parser.add_argument("--workspace", default="pulso-emergency-ops")
    parser.add_argument("--output")
    arguments = parser.parse_args()

    database = SQLiteDatabase(arguments.database) if arguments.database else SQLiteDatabase()
    database.initialize()
    repository = EncounterRepository(database)
    encounters = EncounterService(repository)
    orders = OrderService(repository)

    if arguments.command == "init":
        result: object = {"database": str(database.path), "initialized": True}
    elif arguments.command == "start":
        if not arguments.patient or not arguments.bed:
            parser.error("start requires --patient and --bed")
        result = encounters.start(
            patient_ref=arguments.patient,
            bed=arguments.bed,
            clinician_id=arguments.clinician,
            language=arguments.language,
        ).model_dump(mode="json")
    elif arguments.command == "capture":
        if not arguments.encounter or not arguments.text:
            parser.error("capture requires --encounter and --text")
        result = [
            item.model_dump(mode="json")
            for item in encounters.capture_text(
                arguments.encounter,
                arguments.text,
                speaker=ActorRole(arguments.speaker),
                language=arguments.language,
            )
        ]
    elif arguments.command == "critical":
        if not arguments.encounter:
            parser.error("critical requires --encounter")
        result = encounters.critical_mode(
            arguments.encounter, actor=arguments.clinician
        ).model_dump(mode="json")
    elif arguments.command == "review":
        if not arguments.encounter:
            parser.error("review requires --encounter")
        result = encounters.begin_review(arguments.encounter, actor=arguments.clinician).model_dump(
            mode="json"
        )
    elif arguments.command == "document":
        if not arguments.encounter:
            parser.error("document requires --encounter")
        document = build_document(arguments.encounter, repository.list_events(arguments.encounter))
        result = save_document(
            repository,
            document,
            actor=arguments.clinician,
            signature=arguments.signature,
        ).model_dump(mode="json")
    elif arguments.command.startswith("order-"):
        if not arguments.order:
            parser.error(f"{arguments.command} requires --order")
        if arguments.command == "order-confirm":
            if not arguments.signature:
                parser.error("order-confirm requires --signature")
            result = orders.confirm(
                arguments.order,
                clinician_id=arguments.clinician,
                signature=arguments.signature,
            ).model_dump(mode="json")
        elif arguments.command == "order-dispatch":
            result = orders.dispatch(arguments.order).model_dump(mode="json")
        elif arguments.command == "order-ack":
            result = orders.acknowledge(arguments.order, actor=arguments.clinician).model_dump(
                mode="json"
            )
        elif arguments.command == "order-start":
            result = orders.begin(arguments.order, actor=arguments.clinician).model_dump(
                mode="json"
            )
        elif arguments.command == "order-complete":
            result = orders.complete(arguments.order, actor=arguments.clinician).model_dump(
                mode="json"
            )
        else:
            result = orders.cancel(
                arguments.order,
                actor=arguments.clinician,
                reason=arguments.text or "cancelled by clinician",
            ).model_dump(mode="json")
    elif arguments.command == "dashboard":
        result = repository.dashboard()
    elif arguments.command == "rag-index":
        result = RetrievalService().index()
    elif arguments.command == "rag-search":
        if not arguments.text:
            parser.error("rag-search requires --text")
        result = {"results": RetrievalService().search(arguments.text, arguments.workspace)}
    elif arguments.command == "fhir-export":
        if not arguments.encounter:
            parser.error("fhir-export requires --encounter")
        result = export_bundle(
            repository.get(arguments.encounter),
            repository.list_events(arguments.encounter),
            repository.list_orders(arguments.encounter),
        )
        if arguments.output:
            destination = Path(arguments.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    else:
        result = QvacRuntime().health()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
