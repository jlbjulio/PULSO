"""Local spoken readback for translations and order confirmation."""

from __future__ import annotations

from pathlib import Path

from .runtime import QvacRuntime


class SpeechOutputService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def synthesize(self, text: str, output: str | Path, language: str = "es") -> Path:
        destination = Path(output).resolve()
        self.runtime.run("tts", text=text, output=str(destination), language=language)
        return destination
