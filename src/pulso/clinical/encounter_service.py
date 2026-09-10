from __future__ import annotations

import re
from pathlib import Path

from langdetect import LangDetectException, detect_langs

from pulso.ai.audio import AudioService
from pulso.ai.extraction import ClinicalExtractionService
from pulso.ai.rag import RetrievalService
from pulso.ai.runtime import QvacRuntimeError
from pulso.ai.translation import TranslationService
from pulso.clinical.encounters import Encounter, EncounterState
from pulso.clinical.events import ActorRole, ClinicalEvent, ExtractionResult, Utterance
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
            return self.translation.translate(text, "es", patient_language)
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
        query = self._clinical_text(utterance)
        references = self._reference_context(encounter_id, query, encounter.clinician_id)
        result = self._extract(encounter, [utterance], references)
        events = self._save_events(encounter, result, [utterance])
        if requests_critical_mode(text):
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
            original = str(item.get("text", "")).strip()
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
        query = " ".join(self._clinical_text(item) for item in utterances)
        references = self._reference_context(encounter_id, query, encounter.clinician_id)
        result = self._extract(encounter, utterances, references)
        events = self._save_events(encounter, result, utterances)
        if any(requests_critical_mode(item.original_text) for item in utterances):
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
