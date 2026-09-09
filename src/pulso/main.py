"""PULSO command-line entry point for reproducible backend workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pulso.application.documentation import build_document, save_document
from pulso.application.encounter import EncounterService
from pulso.application.fhir_export import export_bundle
from pulso.application.order_flow import OrderService
from pulso.domain.clinical_events import ActorRole
from pulso.infrastructure.database.sqlite import SQLiteDatabase
from pulso.infrastructure.qvac.retrieval import RetrievalService
from pulso.infrastructure.qvac.runtime import QvacRuntime
from pulso.infrastructure.repositories.encounters import EncounterRepository


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
            "dashboard",
            "rag-index",
            "rag-search",
            "qvac-health",
            "fhir-export",
            "ui",
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

    if arguments.command == "ui":
        from pulso.ui.app import run_app

        run_app()
        return

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
        else:
            result = orders.acknowledge(arguments.order, actor=arguments.clinician).model_dump(
                mode="json"
            )
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
