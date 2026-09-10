
from __future__ import annotations

from .runtime import QvacRuntime


class TranslationService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        return str(
            self.runtime.run(
                "translate",
                text=text,
                source=source_language,
                target=target_language,
            )["translated_text"]
        )

    def to_spanish(self, text: str, source_language: str) -> str:
        if source_language.casefold() == "es":
            return text
        return self.translate(text, source_language, "es")
