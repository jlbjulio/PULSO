from __future__ import annotations

import re
import time
from pathlib import Path

from langdetect import LangDetectException, detect_langs

from pulso.ai.audio import AudioService
from pulso.ai.extraction import ClinicalExtractionService
from pulso.ai.rag import RetrievalService
from pulso.ai.runtime import QvacRuntimeError
from pulso.ai.translation import TranslationService
from pulso.clinical.encounters import Encounter, EncounterState
from pulso.clinical.events import (
    ORDER_TYPES,
    ActorRole,
    ClinicalEvent,
    EventState,
    EventType,
    ExtractionResult,
    Utterance,
)
from pulso.clinical.safety import explicit_command, gate_event
from pulso.storage.repository import EncounterRepository

SUPPORTED_LANGUAGES = {"en", "es", "pt", "fr", "de", "it", "nl", "fi", "cs", "sv"}
PROFESSIONAL_LANGUAGE = re.compile(
    r"\b(paciente|diagn[oó]stico|administr(?:ar|ado)|solicitar|activar|"
    r"presi[oó]n|saturaci[oó]n|frecuencia|evaluaci[oó]n|hallazgo|"
    r"trasladar|interconsulta|c[oó]digo)\b",
    re.IGNORECASE,
)
PATIENT_LANGUAGE = re.compile(
    r"\b(me duele|tengo|siento|no puedo|me cuesta|i have|i feel|i can'?t|my\b)",
    re.IGNORECASE,
)
CRITICAL_COMMAND = re.compile(r"\b(c[oó]digo azul|modo cr[ií]tico)\b", re.IGNORECASE)
ASR_WAKE_WORD = re.compile(
    r"\b(?:puls[oó]|pulse\s+o|ulso)\b(?=\s*[,;:]?\s*"
    r"(?:activar|solicitar|administrar|trasladar|iniciar|llamar|cancelar))",
    re.IGNORECASE,
)
WAKE_WORD_AT_END = re.compile(r"\b(?:puls[oó]|pulse\s+o|ulso)\s*[,;:]?\s*$", re.I)
COMMAND_START = re.compile(
    r"^\s*(?:activar|solicitar|administrar|trasladar|iniciar|llamar|cancelar)\b",
    re.I,
)
PENDING_WAKE_WORDS: dict[str, tuple[ActorRole, float]] = {}


def normalize_clinical_speech(text: str) -> str:
    normalized = ASR_WAKE_WORD.sub("Pulso", text)
    normalized = WAKE_WORD_AT_END.sub("Pulso", normalized)
    normalized = re.sub(r"\bequipo de tramo\b", "equipo de trauma", normalized, flags=re.I)
    normalized = re.sub(r"\bpor\s+t[aá]til\b", "portátil", normalized, flags=re.I)
    normalized = re.sub(r"\b(?:t[oó]rex|torax)\b", "tórax", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip()


def command_context(encounter_id: str, utterances: list[Utterance]) -> list[Utterance]:
    pending = PENDING_WAKE_WORDS.pop(encounter_id, None)
    contextual = utterances
    if pending and utterances:
        role, expires_at = pending
        first = utterances[0]
        if (
            time.monotonic() <= expires_at
            and first.speaker == role
            and COMMAND_START.search(first.original_text)
        ):
            contextual = [
                first.model_copy(update={"original_text": f"Pulso, {first.original_text}"}),
                *utterances[1:],
            ]
    if utterances and WAKE_WORD_AT_END.search(utterances[-1].original_text):
        PENDING_WAKE_WORDS[encounter_id] = (
            utterances[-1].speaker,
            time.monotonic() + 90,
        )
    return contextual


def _order_type(clause: str) -> EventType | None:
    text = clause.casefold()
    imaging_terms = ("radiograf", "tomograf", "rayos x", "ecograf", "resonancia")
    if any(word in text for word in imaging_terms):
        return EventType.IMAGING_ORDER
    laboratory_terms = ("laboratorio", "hemograma", "gasometr", "cultivo")
    if any(word in text for word in laboratory_terms):
        return EventType.LAB_ORDER
    if any(word in text for word in ("código azul", "codigo azul", "reanimación")):
        return EventType.CODE_EVENT
    if any(
        word in text
        for word in (
            "equipo",
            "psicolog",
            "psiquiatr",
            "cardiolog",
            "neurolog",
            "ciruj",
            "trabajo social",
            "terapeuta",
        )
    ):
        return EventType.CONSULT_ORDER
    if any(word in text for word in ("traslad", "transfer")):
        return EventType.TRANSFER
    if any(word in text for word in ("administrar", "medicamento", " mg", " ml")):
        return EventType.MEDICATION_ORDER
    if any(word in text for word in ("procedimiento", "intubar", "canalizar")):
        return EventType.PROCEDURE_ORDER
    return None


def explicit_order_events(
    encounter: Encounter,
    utterances: list[Utterance],
) -> list[ClinicalEvent]:
    events: list[ClinicalEvent] = []
    authorized = {ActorRole.PHYSICIAN, ActorRole.NURSE, ActorRole.PARAMEDIC}
    for utterance in utterances:
        command = explicit_command(utterance.original_text)
        if not command or utterance.speaker not in authorized:
            continue
        clauses = re.split(
            r"\s+y\s+(?=(?:activar|solicitar|administrar|trasladar|iniciar|llamar)\b)|[.;]",
            command,
            flags=re.I,
        )
        for clause in (part.strip(" ,") for part in clauses):
            event_type = _order_type(clause)
            if event_type is None:
                continue
            events.append(
                ClinicalEvent(
                    encounter_id=encounter.id,
                    type=event_type,
                    state=EventState.PENDING_CONFIRMATION,
                    actor_role=utterance.speaker,
                    patient_ref=encounter.patient_ref,
                    evidence_utterance_ids=[utterance.id],
                    payload={"request": clause},
                    actionable=True,
                    confirmation_required=True,
                    confidence=1.0,
                )
            )
    return events


def detect_language(text: str, fallback: str = "es") -> str:
    try:
        candidates = detect_langs(text)
    except LangDetectException:
        return fallback
    if not candidates or candidates[0].prob < 0.80:
        return fallback
    language = candidates[0].lang
    return language if language in SUPPORTED_LANGUAGES else fallback


def infer_role(text: str) -> ActorRole:
    if explicit_command(text) or PROFESSIONAL_LANGUAGE.search(text):
        return ActorRole.PHYSICIAN
    if PATIENT_LANGUAGE.search(text):
        return ActorRole.PATIENT
    return ActorRole.UNKNOWN


def requests_critical_mode(text: str) -> bool:
    command = explicit_command(text)
    return bool(command and CRITICAL_COMMAND.search(command))


class EncounterService:
    def __init__(
        self,
        repository: EncounterRepository,
        extraction: ClinicalExtractionService | None = None,
        audio: AudioService | None = None,
        translation: TranslationService | None = None,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self.repository = repository
        self.extraction = extraction or ClinicalExtractionService()
        self.audio = audio or AudioService()
        self.translation = translation or TranslationService()
        self.retrieval = retrieval or RetrievalService()

    def _conversation_translation(
        self,
        text: str,
        source_language: str,
        patient_language: str,
    ) -> str | None:
        if source_language != "es":
            return self.translation.to_spanish(text, source_language)
        if patient_language != "es":
            patient_facing_text = re.split(r"\bpulso\b", text, maxsplit=1, flags=re.I)[0]
            patient_facing_text = patient_facing_text.strip(" .,;:")
            if patient_facing_text:
                return self.translation.translate(
                    patient_facing_text,
                    "es",
                    patient_language,
                )
        return None

    @staticmethod
    def _clinical_text(utterance: Utterance) -> str:
        if utterance.language != "es" and utterance.translated_text:
            return utterance.translated_text
        return utterance.original_text

    def start(
        self, *, patient_ref: str, bed: str, clinician_id: str, language: str = "es"
    ) -> Encounter:
        return self.repository.create(
            Encounter(
                patient_ref=patient_ref,
                bed=bed,
                clinician_id=clinician_id,
                language=language,
            )
        )

    def _reference_context(self, encounter_id: str, query: str, actor: str) -> list[dict]:
        normalized = query.casefold()
        medication_terms = [
            "medicamento",
            "medicación",
            "dosis",
            "administr",
            "antibiótico",
            "mg",
            "ml",
            "vía iv",
        ]
        emergency_terms = [
            "pulso",
            "código",
            "trauma",
            "sepsis",
            "ictus",
            "reanimación",
            "traslad",
            "transferencia",
            "interconsulta",
        ]
        workflow_terms = ["pulso", "orden", "solicitar", "traslad", "resultado"]
        has_medication = any(term in normalized for term in medication_terms)
        has_emergency = any(term in normalized for term in emergency_terms)
        has_workflow = any(term in normalized for term in workflow_terms)
        workspaces: list[str] = []
        if has_emergency or has_workflow:
            workspaces.append("pulso-emergency-ops")
        if has_medication:
            workspaces.append("pulso-medication-safety")
        if has_workflow:
            workspaces.append("pulso-fhir-interop")
        if not workspaces:
            return []
        results: list[dict] = []
        try:
            for workspace in workspaces:
                results.extend(self.retrieval.search(query, workspace=workspace, top_k=2))
        except QvacRuntimeError:
            return []
        results = [
            {
                "content": str(item.get("content") or item.get("text") or "")[:800],
                "score": item.get("score"),
                "metadata": item.get("metadata", {}),
            }
            for item in results
        ]
        self.repository.save_rag_check(
            encounter_id,
            query=query,
            results=results,
            actor=actor,
        )
        return results

    def _extract(
        self,
        encounter: Encounter,
        utterances: list[Utterance],
        references: list[dict],
    ) -> ExtractionResult:
        return self.extraction.extract(encounter, utterances, references)

    def _save_events(
        self,
        encounter: Encounter,
        result: ExtractionResult,
        utterances: list[Utterance],
    ) -> list[ClinicalEvent]:
        evidence = {item.id: self._clinical_text(item) for item in utterances}
        gated = [
            gate_event(
                event,
                [evidence[item] for item in event.evidence_utterance_ids if item in evidence],
            )
            for event in result.events
        ]
        gated = [event for event in gated if event.type not in ORDER_TYPES or event.actionable]
        for event in gated:
            self.repository.save_event(event, actor=encounter.clinician_id)
        return gated

    def capture_text(
        self,
        encounter_id: str,
        text: str,
        *,
        speaker: ActorRole,
        language: str = "auto",
        translated_text: str | None = None,
    ) -> list[ClinicalEvent]:
        encounter = self.repository.get(encounter_id)
        if encounter.state not in {EncounterState.ACTIVE, EncounterState.CRITICAL}:
            raise ValueError("capture is only available during an active encounter")
        text = normalize_clinical_speech(text)
        resolved_speaker = infer_role(text) if speaker == ActorRole.UNKNOWN else speaker
        fallback_language = encounter.language if resolved_speaker == ActorRole.PATIENT else "es"
        resolved_language = (
            detect_language(text, fallback_language) if language == "auto" else language
        )
        if resolved_speaker == ActorRole.PATIENT and resolved_language != "es":
            if encounter.language != resolved_language:
                encounter = self.repository.update_language(
                    encounter_id,
                    resolved_language,
                    actor=encounter.clinician_id,
                )
        translated = translated_text
        if not translated:
            translated = self._conversation_translation(
                text,
                resolved_language,
                encounter.language,
            )
        utterance = Utterance(
            speaker=resolved_speaker,
            language=resolved_language,
            original_text=text,
            translated_text=translated,
        )
        self.repository.add_utterance(encounter_id, utterance)
        processing_utterances = command_context(encounter_id, [utterance])
        query = self._clinical_text(processing_utterances[0])
        references = self._reference_context(encounter_id, query, encounter.clinician_id)
        result = self._extract(encounter, processing_utterances, references)
        commands = explicit_order_events(encounter, processing_utterances)
        if commands:
            result.events = [event for event in result.events if event.type not in ORDER_TYPES]
            result.events.extend(commands)
        events = self._save_events(encounter, result, processing_utterances)
        if any(requests_critical_mode(item.original_text) for item in processing_utterances):
            self.critical_mode(encounter_id, actor=encounter.clinician_id)
        return events

    def capture_audio(self, encounter_id: str, audio_path: str | Path) -> list[ClinicalEvent]:
        encounter = self.repository.get(encounter_id)
        if encounter.state not in {EncounterState.ACTIVE, EncounterState.CRITICAL}:
            raise ValueError("capture is only available during an active encounter")
        analysis = self.audio.analyze(audio_path)
        detected_items = [
            item for item in analysis.get("utterances", []) if str(item.get("text", "")).strip()
        ]
        speaker_texts: dict[str, list[str]] = {}
        for item in detected_items:
            speaker_texts.setdefault(str(item.get("speaker", "unknown")), []).append(
                str(item.get("text", ""))
            )
        speaker_roles = {
            speaker: infer_role(" ".join(texts)) for speaker, texts in speaker_texts.items()
        }
        detected: list[tuple[dict, str, ActorRole, str]] = []
        patient_language = encounter.language
        for item in detected_items:
            original = normalize_clinical_speech(str(item.get("text", "")).strip())
            role = infer_role(original)
            if role == ActorRole.UNKNOWN:
                role = speaker_roles.get(str(item.get("speaker", "unknown")), ActorRole.UNKNOWN)
            fallback_language = patient_language if role == ActorRole.PATIENT else "es"
            language = detect_language(original, fallback_language)
            if role == ActorRole.PATIENT and language != "es":
                patient_language = language
            detected.append((item, original, role, language))
        if patient_language != encounter.language:
            encounter = self.repository.update_language(
                encounter_id,
                patient_language,
                actor=encounter.clinician_id,
            )
        utterances: list[Utterance] = []
        for item, original, role, language in detected:
            translated = None
            try:
                translated = self._conversation_translation(
                    original,
                    language,
                    patient_language,
                )
            except QvacRuntimeError:
                translated = None
            utterance = Utterance(
                speaker=role,
                language=language,
                original_text=original,
                translated_text=translated,
                started_at_ms=int(item.get("start_ms", 0)),
                ended_at_ms=int(item.get("end_ms", 0)),
            )
            self.repository.add_utterance(encounter_id, utterance)
            utterances.append(utterance)
        if not utterances:
            raise ValueError("no speech was detected")
        processing_utterances = command_context(encounter_id, utterances)
        query = " ".join(self._clinical_text(item) for item in processing_utterances)
        references = self._reference_context(encounter_id, query, encounter.clinician_id)
        result = self._extract(encounter, processing_utterances, references)
        commands = explicit_order_events(encounter, processing_utterances)
        if commands:
            result.events = [event for event in result.events if event.type not in ORDER_TYPES]
            result.events.extend(commands)
        events = self._save_events(encounter, result, processing_utterances)
        if any(requests_critical_mode(item.original_text) for item in processing_utterances):
            self.critical_mode(encounter_id, actor=encounter.clinician_id)
        return events

    def critical_mode(self, encounter_id: str, *, actor: str) -> Encounter:
        return self.repository.set_state(encounter_id, EncounterState.CRITICAL, actor=actor)

    def begin_review(self, encounter_id: str, *, actor: str) -> Encounter:
        return self.repository.set_state(encounter_id, EncounterState.REVIEW, actor=actor)

    def close(self, encounter_id: str, *, actor: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter.state != EncounterState.REVIEW:
            raise ValueError("the encounter must be reviewed before closing")
        return self.repository.set_state(encounter_id, EncounterState.CLOSED, actor=actor)
