"""OCR with block-level evidence coordinates."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pymupdf

from .runtime import QvacRuntime


class DocumentService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime()

    def read(self, image_path: str | Path) -> list[dict[str, Any]]:
        path = Path(image_path).resolve()
        if path.suffix.casefold() != ".pdf":
            return self.runtime.run("ocr", image=str(path))["blocks"]
        with TemporaryDirectory(prefix="pulso-ocr-") as directory:
            images: list[str] = []
            with pymupdf.open(path) as document:
                for page_number, page in enumerate(document):
                    output = Path(directory) / f"page-{page_number + 1}.png"
                    page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(output)
                    images.append(str(output))
            result = self.runtime.run("ocr-batch", images_json=images)["documents"]
        blocks: list[dict[str, Any]] = []
        for page_number, page in enumerate(result, start=1):
            for block in page.get("blocks", []):
                blocks.append({**block, "page": page_number})
        return blocks
