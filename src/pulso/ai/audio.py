
from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import QvacRuntime


class AudioService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def analyze(self, path: str | Path) -> dict[str, Any]:
        return self.runtime.run("audio-pipeline", audio=str(Path(path).resolve()))
