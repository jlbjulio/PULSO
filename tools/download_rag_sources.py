from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = ROOT / "data" / "rag"
MANIFEST = RAG_ROOT / "manifest.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "PULSO/1.0 local-RAG"})
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def main() -> None:
    sources = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    downloaded = 0
    verified = 0
    failures: list[str] = []
    for source in sources:
        if not source.get("include_in_rag", True):
            continue
        destination = RAG_ROOT / Path(source["local_path"])
        expected = str(source.get("sha256", ""))
        if destination.is_file() and (not expected or digest(destination) == expected):
            verified += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".download")
        try:
            download(str(source["source_url"]), temporary)
            if expected and digest(temporary) != expected:
                raise ValueError("checksum does not match the manifest")
            temporary.replace(destination)
            downloaded += 1
            time.sleep(0.1)
        except Exception as error:
            temporary.unlink(missing_ok=True)
            failures.append(f"{source['id']}: {error}")
    print(f"Verified sources: {verified}")
    print(f"Downloaded sources: {downloaded}")
    if failures:
        raise SystemExit("These sources could not be prepared:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
