from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESPONSE_PREFIX = "__PULSO__"


class QvacRuntimeError(RuntimeError):
    pass


class QvacRuntime:
    _process: subprocess.Popen[str] | None = None
    _lock = threading.Lock()

    def __init__(self, timeout_seconds: int = 600) -> None:
        self.timeout_seconds = timeout_seconds

    @classmethod
    def _start(cls) -> subprocess.Popen[str]:
        if cls._process and cls._process.poll() is None:
            return cls._process
        node = shutil.which("node")
        runner = PROJECT_ROOT / "node_modules" / "tsx" / "dist" / "cli.mjs"
        if not node or not runner.exists():
            raise QvacRuntimeError("Node.js or tsx was not found; run npm install")
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        cls._process = subprocess.Popen(
            [node, str(runner), "src/qvac/cli.ts", "server"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            env=environment,
        )
        return cls._process

    @classmethod
    def close(cls) -> None:
        process = cls._process
        cls._process = None
        if not process or process.poll() is not None:
            return
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.terminate()

    def run(self, command: str, **options: object) -> dict[str, Any]:
        request = json.dumps(
            {"command": command, "options": options},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._lock:
            process = self._start()
            if not process.stdin or not process.stdout:
                raise QvacRuntimeError("QVAC worker streams are unavailable")
            try:
                process.stdin.write(request + "\n")
                process.stdin.flush()
                while True:
                    line = process.stdout.readline()
                    if not line:
                        self.close()
                        raise QvacRuntimeError("QVAC worker stopped unexpectedly")
                    if not line.startswith(RESPONSE_PREFIX):
                        continue
                    response = json.loads(line[len(RESPONSE_PREFIX) :])
                    if not response.get("ok"):
                        raise QvacRuntimeError(response.get("error") or "local QVAC command failed")
                    return response.get("data", {})
            except (BrokenPipeError, OSError, json.JSONDecodeError) as error:
                self.close()
                raise QvacRuntimeError(str(error)) from error

    def health(self) -> dict[str, Any]:
        return self.run("health")

    def warmup(self) -> dict[str, Any]:
        return self.run("warmup")


atexit.register(QvacRuntime.close)
