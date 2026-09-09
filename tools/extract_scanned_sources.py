"""Use local QVAC OCR for declared PDF pages that have no embedded text."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pymupdf

from pulso.infrastructure.qvac.runtime import QvacRuntime

ROOT = Path(__file__).resolve().parent.parent
RAG = ROOT / "data" / "rag"
CACHE_PATH = RAG / "index" / "ocr-cache.json"
TEMP = ROOT / "runtime-data" / "rag-ocr"


def main() -> None:
    manifest = json.loads((RAG / "manifest.json").read_text(encoding="utf-8-sig"))
    TEMP.mkdir(parents=True, exist_ok=True)
    rendered: list[tuple[str, str, Path]] = []
    for source in manifest:
        path = RAG / Path(source["local_path"])
        if path.suffix.casefold() != ".pdf":
            continue
        document = pymupdf.open(path)
        if any(page.get_text("text").strip() for page in document):
            continue
        for index, page in enumerate(document):
            output = TEMP / f"{source['id']}-page-{index + 1}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(output)
            rendered.append((source["id"], f"page:{index + 1}", output))
    result = QvacRuntime(timeout_seconds=3600).run(
        "ocr-batch", images_json=[str(item[2]) for item in rendered]
    )
    by_path = {Path(item["path"]).resolve(): item["blocks"] for item in result["documents"]}
    cache = {
        f"{source_id}:{locator}": " ".join(
            str(block.get("text", "")) for block in by_path[path.resolve()]
        ).strip()
        for source_id, locator, path in rendered
    }
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(TEMP)
    print(json.dumps({"pages": len(cache), "cache": str(CACHE_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
