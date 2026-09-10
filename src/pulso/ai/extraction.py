
from __future__ import annotations

from pulso.clinical.encounters import Encounter
from pulso.clinical.events import ClinicalEvent, ExtractionResult, Utterance

from .runtime import QvacRuntime


class ClinicalExtractionService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def extract(
        self,
        encounter: Encounter,
        utterances: list[Utterance],
        reference_context: list[dict] | None = None,
    ) -> ExtractionResult:
        def clinical_text(item: Utterance) -> str:
            if item.language != "es" and item.translated_text:
                return item.translated_text
            return item.original_text

        payload = {
            "case_id": encounter.id,
            "patient_ref": encounter.patient_ref,
            "utterances": [
                {
                    "id": item.id,
                    "speaker": item.speaker.value,
                    "language": item.language,
                    "text": clinical_text(item),
                }
                for item in utterances
            ],
            "reference_context": reference_context or [],
        }
        raw = self.runtime.run("extract", input_json=payload)
        events = [
            ClinicalEvent(
                encounter_id=encounter.id,
                source_event_id=item.pop("event_id", None),
                **item,
            )
            for item in raw.get("events", [])
        ]
        return ExtractionResult(
            events=events,
            ignored_utterance_ids=raw.get("ignored_utterance_ids", []),
            session_flags=raw.get("session_flags", []),
        )
