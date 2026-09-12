from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_NODE = (22, 17, 0)


def run(*command: str) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def npm_executable() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("npm was not found in PATH.")
    return npm


def node_version() -> tuple[int, int, int]:
    node = shutil.which("node")
    if not node or not npm_executable():
        raise SystemExit("Install Node.js 22.17 or newer before continuing.")
    output = subprocess.check_output([node, "--version"], text=True).strip()
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", output)
    if not match:
        raise SystemExit(f"Could not parse the Node.js version: {output}")
    return tuple(int(value) for value in match.groups())


def validate_models() -> None:
    config = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))
    missing: list[str] = []
    for model in config["models"].values():
        for key, value in model.items():
            required_path = key.endswith("path") and key != "lora_path"
            if isinstance(value, str) and (required_path or key == "euro"):
                if not (ROOT / value).exists():
                    missing.append(value)
    if missing:
        raise SystemExit("Missing models:\n" + "\n".join(missing))


def validate_rag_sources() -> None:
    manifest_path = ROOT / "data" / "rag" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    failures: list[str] = []
    included = 0
    for source in manifest:
        if not source.get("include_in_rag", True):
            continue
        included += 1
        path = ROOT / "data" / "rag" / Path(source["local_path"])
        if not path.is_file():
            failures.append(f"missing: {source['filename']}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            failures.append(f"invalid checksum: {source['filename']}")
    if failures:
        raise SystemExit("Invalid RAG sources:\n" + "\n".join(failures))
    print(f"Verified RAG sources: {included}")


def main() -> None:
    if os.environ.get("VIRTUAL_ENV") or sys.prefix != sys.base_prefix:
        raise SystemExit("Exit the virtual environment. This project uses system Python.")
    if (sys.version_info.major, sys.version_info.minor) < (3, 11):
        raise SystemExit("Python 3.11 or newer is required.")
    if node_version() < MINIMUM_NODE:
        raise SystemExit("Node.js 22.17 or newer is required.")

    run(sys.executable, "-m", "pip", "install", "-r", "python-requirements.txt")
    run(sys.executable, "-m", "pip", "install", "--editable", ".")
    npm = npm_executable()
    run(npm, "ci")
    run(npm, "run", "models:download")
    run(npm, "run", "rag:download")
    validate_models()
    validate_rag_sources()
    run(npm, "run", "rag:prepare")
    run(sys.executable, "-m", "pulso.main", "init")
    run(npm, "run", "rag:reset")
    run(npm, "run", "rag:index")
    run(npm, "run", "check")
    print("\nPULSO is ready. Run: npm run app")


if __name__ == "__main__":
    main()
