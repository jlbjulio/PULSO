"""Local transcription and speaker diarization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import QvacRuntime


class AudioService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def transcribe(self, path: str | Path) -> dict[str, Any]:
        return self.runtime.run("transcribe", audio=str(Path(path).resolve()))

    def diarize(self, path: str | Path) -> list[dict[str, Any]]:
        return self.runtime.run("diarize", audio=str(Path(path).resolve()))["segments"]

    def analyze(self, path: str | Path) -> dict[str, Any]:
        return self.runtime.run("audio-pipeline", audio=str(Path(path).resolve()))
