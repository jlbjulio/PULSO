"""Small Python boundary around the local TypeScript QVAC runtime."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class QvacRuntimeError(RuntimeError):
    pass


class QvacRuntime:
    def __init__(self, timeout_seconds: int = 600) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, command: str, **options: object) -> dict[str, Any]:
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if not npx:
            raise QvacRuntimeError("npx was not found")
        arguments = [npx, "--no-install", "tsx", "src/qvac/cli.ts", command]
        for name, value in options.items():
            if value is None:
                continue
            if isinstance(value, dict | list):
                value = json.dumps(value, ensure_ascii=False)
            arguments.extend([f"--{name.replace('_', '-')}", str(value)])
        completed = subprocess.run(
            arguments,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise QvacRuntimeError(message or "local QVAC command failed")
        for line in reversed(completed.stdout.splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        raise QvacRuntimeError("QVAC returned no JSON result")

    def health(self) -> dict[str, Any]:
        return self.run("health")
