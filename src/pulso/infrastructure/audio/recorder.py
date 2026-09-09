"""Single-button microphone recorder that writes local 16 kHz PCM WAV."""

from __future__ import annotations

import threading
import wave
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[4]


class MicrophoneRecorder:
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self.recording:
            return
        self._frames = []

        def callback(data: np.ndarray, _frames: int, _time: object, status: object) -> None:
            if status:
                return
            with self._lock:
                self._frames.append(data.copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> Path:
        if not self._stream:
            raise RuntimeError("the microphone is not recording")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            samples = np.concatenate(self._frames, axis=0) if self._frames else np.empty((0, 1))
        if samples.size == 0:
            raise RuntimeError("no audio was captured")
        directory = ROOT / "runtime-data" / "recordings"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"encounter-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(samples.astype(np.int16).tobytes())
        return path
