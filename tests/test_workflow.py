from pulso.clinical.documentation import build_document, save_document
from pulso.clinical.encounter_service import EncounterService
from pulso.clinical.encounters import Encounter
from pulso.clinical.events import ActorRole, ClinicalEvent, EventState, EventType
from pulso.clinical.fhir import export_bundle
from pulso.clinical.order_service import OrderService
from pulso.clinical.orders import OrderState
from pulso.storage.audit import verify_audit_chain
from pulso.storage.database import SQLiteDatabase
from pulso.storage.repository import EncounterRepository


def actionable_event(encounter: Encounter) -> ClinicalEvent:
    return ClinicalEvent(
        encounter_id=encounter.id,
        source_event_id="e1",
        type=EventType.IMAGING_ORDER,
        state=EventState.PENDING_CONFIRMATION,
        actor_role=ActorRole.PHYSICIAN,
        patient_ref=encounter.patient_ref,
        evidence_utterance_ids=["u1"],
        payload={"explicit_command": "solicitar radiografía portátil de tórax"},
        actionable=True,
        confirmation_required=True,
    )


def test_closed_loop_order_is_audited_and_queued(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "pulso.db")
    database.initialize()
    repository = EncounterRepository(database)
    encounter = repository.create(
        Encounter(patient_ref="DEMO-1", bed="Trauma 2", clinician_id="dra.rivera")
    )
    event = actionable_event(encounter)
    repository.save_event(event, actor="dra.rivera")
    service = OrderService(repository)
    draft = service.draft_from_event(event, actor="dra.rivera")
    assert draft.state == OrderState.AWAITING_CONFIRMATION
    confirmed = service.confirm(draft.id, clinician_id="dra.rivera", signature="local:sig")
    dispatched = service.dispatch(confirmed.id)
    assert dispatched.state == OrderState.DISPATCHED
    accepted = service.acknowledge(dispatched.id, actor="imagenologia")
    started = service.begin(accepted.id, actor="imagenologia")
    completed = service.complete(started.id, actor="imagenologia")
    assert completed.state == OrderState.COMPLETED
    with database.connect() as connection:
        assert verify_audit_chain(connection)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sync_outbox WHERE event_type='order.confirmed'"
            ).fetchone()[0]
            == 1
        )


def test_idempotency_prevents_duplicate_order(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "pulso.db")
    database.initialize()
    repository = EncounterRepository(database)
    encounter = repository.create(Encounter(patient_ref="P", bed="1", clinician_id="D"))
    candidate = actionable_event(encounter)
    repository.save_event(candidate, actor="D")
    service = OrderService(repository)
    service.draft_from_event(candidate, actor="D")
    try:
        service.draft_from_event(candidate, actor="D")
    except Exception as error:
        assert "UNIQUE" in str(error)
    else:
        raise AssertionError("duplicate order was persisted")


def test_document_contains_only_persisted_event_payloads() -> None:
    symptom = ClinicalEvent(
        encounter_id="enc",
        type=EventType.SYMPTOM,
        state=EventState.REPORTED,
        actor_role=ActorRole.PATIENT,
        evidence_utterance_ids=["u1"],
        payload={"name": "dolor torácico", "severity": "8/10"},
    )
    document = build_document("enc", [symptom])
    assert "dolor torácico" in document.summary
    assert not document.assessments
    assert not document.interventions


def test_fhir_export_keeps_evidence_provenance() -> None:
    encounter = Encounter(patient_ref="DEMO 1", bed="Trauma 2", clinician_id="dra.rivera")
    event = ClinicalEvent(
        encounter_id=encounter.id,
        type=EventType.SYMPTOM,
        state=EventState.REPORTED,
        actor_role=ActorRole.PATIENT,
        evidence_utterance_ids=["u1"],
        payload={"name": "dolor torácico"},
    )
    bundle = export_bundle(encounter, [event], [])
    resources = [entry["resource"] for entry in bundle["entry"]]
    assert any(item["resourceType"] == "Observation" for item in resources)
    provenance = next(item for item in resources if item["resourceType"] == "Provenance")
    assert provenance["entity"][0]["what"]["identifier"]["value"] == "u1"


def test_signed_review_closes_the_encounter(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "pulso.db")
    database.initialize()
    repository = EncounterRepository(database)
    encounter = repository.create(Encounter(patient_ref="P", bed="2", clinician_id="D"))
    service = EncounterService(repository)
    reviewed = service.begin_review(encounter.id, actor="D")
    document = save_document(
        repository,
        build_document(encounter.id, []),
        actor="D",
        signature="local:D",
    )
    closed = service.close(reviewed.id, actor="D")
    assert document.signed_by == "D"
    assert closed.state.value == "closed"
