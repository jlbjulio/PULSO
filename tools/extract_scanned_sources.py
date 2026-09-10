
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from pulso.ai.runtime import QvacRuntime

ROOT = Path(__file__).resolve().parent.parent
RAG = ROOT / "data" / "rag"
CACHE_PATH = RAG / "index" / "ocr-cache.json"


def main() -> None:
    manifest = json.loads((RAG / "manifest.json").read_text(encoding="utf-8-sig"))
    cache = (
        json.loads(CACHE_PATH.read_text(encoding="utf-8-sig")) if CACHE_PATH.exists() else {}
    )
    with TemporaryDirectory(prefix="pulso-rag-ocr-") as directory:
        rendered: list[tuple[str, str, Path]] = []
        for source in manifest:
            if not source.get("include_in_rag", True):
                continue
            path = RAG / Path(source["local_path"])
            if path.suffix.casefold() != ".pdf":
                continue
            with pymupdf.open(path) as document:
                for index, page in enumerate(document):
                    locator = f"page:{index + 1}"
                    key = f"{source['id']}:{locator}"
                    if page.get_text("text").strip() or cache.get(key):
                        continue
                    output = Path(directory) / f"{source['id']}-page-{index + 1}.png"
                    page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(output)
                    rendered.append((source["id"], locator, output))
        if rendered:
            result = QvacRuntime(timeout_seconds=3600).run(
                "ocr-batch", images_json=[str(item[2]) for item in rendered]
            )
            by_path = {
                Path(item["path"]).resolve(): item["blocks"] for item in result["documents"]
            }
            for source_id, locator, path in rendered:
                cache[f"{source_id}:{locator}"] = " ".join(
                    str(block.get("text", "")) for block in by_path[path.resolve()]
                ).strip()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"cached_pages": len(cache), "new_pages": len(rendered), "cache": str(CACHE_PATH)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
