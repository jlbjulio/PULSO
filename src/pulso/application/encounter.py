"""Orchestration for capture, extraction, review, and critical mode."""

from __future__ import annotations

from pathlib import Path

from langdetect import LangDetectException, detect

from pulso.domain.clinical_events import ActorRole, ClinicalEvent, Utterance
from pulso.domain.encounters import Encounter, EncounterState
from pulso.domain.safety import gate_event
from pulso.infrastructure.qvac.audio import AudioService
from pulso.infrastructure.qvac.clinical import ClinicalExtractionService
from pulso.infrastructure.qvac.runtime import QvacRuntimeError
from pulso.infrastructure.qvac.translation import TranslationService
from pulso.infrastructure.repositories.encounters import EncounterRepository


class EncounterService:
    def __init__(
        self,
        repository: EncounterRepository,
        extraction: ClinicalExtractionService | None = None,
        audio: AudioService | None = None,
        translation: TranslationService | None = None,
    ) -> None:
        self.repository = repository
        self.extraction = extraction or ClinicalExtractionService()
        self.audio = audio or AudioService()
        self.translation = translation or TranslationService()

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

    def capture_text(
        self,
        encounter_id: str,
        text: str,
        *,
        speaker: ActorRole,
        language: str = "es",
        translated_text: str | None = None,
    ) -> list[ClinicalEvent]:
        encounter = self.repository.get(encounter_id)
        if encounter.state not in {EncounterState.ACTIVE, EncounterState.CRITICAL}:
            raise ValueError("capture is only available during an active encounter")
        utterance = Utterance(
            speaker=speaker,
            language=language,
            original_text=text,
            translated_text=translated_text,
        )
        self.repository.add_utterance(encounter_id, utterance)
        result = self.extraction.extract(encounter, [utterance])
        evidence = [translated_text or text]
        gated = [gate_event(event, evidence) for event in result.events]
        for event in gated:
            self.repository.save_event(event, actor=encounter.clinician_id)
        return gated

    def capture_audio(self, encounter_id: str, audio_path: str | Path) -> list[ClinicalEvent]:
        encounter = self.repository.get(encounter_id)
        if encounter.state not in {EncounterState.ACTIVE, EncounterState.CRITICAL}:
            raise ValueError("capture is only available during an active encounter")
        analysis = self.audio.analyze(audio_path)
        utterances: list[Utterance] = []
        for item in analysis.get("utterances", []):
            original = str(item.get("text", "")).strip()
            if not original:
                continue
            try:
                language = detect(original)
            except LangDetectException:
                language = "unknown"
            translated = None
            if language not in {"es", "unknown"}:
                try:
                    translated = self.translation.to_spanish(original, language)
                except QvacRuntimeError:
                    translated = None
            utterance = Utterance(
                speaker=ActorRole.UNKNOWN,
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
        result = self.extraction.extract(encounter, utterances)
        evidence_by_id = {
            item.id: item.translated_text or item.original_text for item in utterances
        }
        gated = [
            gate_event(
                event,
                [
                    evidence_by_id[item]
                    for item in event.evidence_utterance_ids
                    if item in evidence_by_id
                ],
            )
            for event in result.events
        ]
        for event in gated:
            self.repository.save_event(event, actor=encounter.clinician_id)
        return gated

    def critical_mode(self, encounter_id: str, *, actor: str) -> Encounter:
        return self.repository.set_state(encounter_id, EncounterState.CRITICAL, actor=actor)

    def begin_review(self, encounter_id: str, *, actor: str) -> Encounter:
        return self.repository.set_state(encounter_id, EncounterState.REVIEW, actor=actor)
