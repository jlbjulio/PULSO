"""OCR with block-level evidence coordinates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import QvacRuntime


class DocumentService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def read(self, image_path: str | Path) -> list[dict[str, Any]]:
        return self.runtime.run("ocr", image=str(Path(image_path).resolve()))["blocks"]
