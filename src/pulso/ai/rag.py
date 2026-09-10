
from __future__ import annotations

from typing import Any

from .runtime import QvacRuntime


class RetrievalService:
    def __init__(self, runtime: QvacRuntime | None = None) -> None:
        self.runtime = runtime or QvacRuntime(timeout_seconds=1800)

    def index(self, corpus_path: str | None = None) -> dict[str, Any]:
        return self.runtime.run("rag-index", corpus=corpus_path)

    def search(self, query: str, workspace: str = "pulso-clinical", top_k: int = 5) -> list[dict]:
        return self.runtime.run("rag-search", query=query, workspace=workspace, top_k=top_k)[
            "results"
        ]
