"""Train PULSO's MedPsy event-extraction adapter and log it locally."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from tensorboardX import SummaryWriter

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "clinical" / "medpsy-1.7b-q8_0.gguf"
TRAIN = ROOT / "data" / "finetuning" / "train.jsonl"
VALIDATION = ROOT / "data" / "finetuning" / "validation.jsonl"
OUTPUT = ROOT / "training" / "output"
ADAPTER = OUTPUT / "pulso-medpsy-lora.gguf"
REQUEST = OUTPUT / "training-request.json"
REPORT = OUTPUT / "training-report.json"
BRIDGE = ROOT / "training" / "qvac_finetune.ts"

LORA_CONFIG = {
    "loraRank": 8,
    "loraAlpha": 16,
    "loraSeed": 42,
    "loraModules": "attn_q,attn_k,attn_v,attn_o",
}
TRAINING_CONFIG = {
    "numberOfEpochs": 1,
    "learningRate": 0.00005,
    "lrScheduler": "cosine",
    "lrMin": 1e-8,
    "warmupRatio": 0.05,
    "warmupRatioSet": True,
    "contextLength": 1536,
    "batchSize": 256,
    "microBatchSize": 64,
    "assistantLossOnly": True,
    "checkpointSaveSteps": 0,
    "weightDecay": 0.01,
}


def count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)


def tensorboard() -> Path:
    logs = OUTPUT / "tensorboard"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tensorboard.main",
            "--logdir",
            str(logs),
            "--host",
            "127.0.0.1",
            "--port",
            "6006",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    webbrowser.open_new_tab("http://127.0.0.1:6006")
    return logs


def train() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate_adapter = OUTPUT / f"pulso-medpsy-lora-{run_id}.gguf"
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx is required; install the Node dependencies first")
    request = {
        "modelPath": str(MODEL),
        "trainPath": str(TRAIN),
        "validationPath": str(VALIDATION),
        "adapterPath": str(candidate_adapter),
        "modelConfig": {"device": "gpu", "ctx_size": 1536, "gpu_layers": 20},
        "options": {**TRAINING_CONFIG, **LORA_CONFIG},
    }
    REQUEST.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    train_count, validation_count = count(TRAIN), count(VALIDATION)
    print(f"Training PULSO MedPsy LoRA: train={train_count}, validation={validation_count}")
    process = subprocess.Popen(
        [npx, "--no-install", "tsx", str(BRIDGE), str(REQUEST)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result: dict[str, object] = {}
    last_event: dict[str, object] = {}
    assert process.stdout is not None
    with SummaryWriter(str(tensorboard() / run_id)) as writer:
        for line in process.stdout:
            line = line.rstrip()
            if line.startswith("PULSO_PROGRESS "):
                event = json.loads(line.removeprefix("PULSO_PROGRESS "))
                step = int(event["global_steps"])
                if event.get("loss") is not None:
                    writer.add_scalar("training/loss", float(event["loss"]), step)
                if event.get("accuracy") is not None:
                    writer.add_scalar("training/accuracy", float(event["accuracy"]), step)
                last_event = event
                print(
                    f"epoch={int(event['current_epoch']) + 1} step={step} "
                    f"batch={event.get('current_batch')}/{event.get('total_batches')} "
                    f"loss={event.get('loss')} accuracy={event.get('accuracy')} "
                    f"eta={round(float(event.get('eta_ms', 0)) / 60000, 1)}m"
                )
            elif line.startswith("PULSO_RESULT "):
                result = json.loads(line.removeprefix("PULSO_RESULT "))
            else:
                print(line)
    if process.wait() != 0:
        raise RuntimeError("QVAC fine-tuning failed")
    if result.get("status") != "COMPLETED" or not candidate_adapter.exists():
        raise RuntimeError(f"fine-tuning did not create {candidate_adapter}")
    candidate_adapter.replace(ADAPTER)
    report = {
        "completed_at": datetime.now().astimezone().isoformat(),
        "base_model": str(MODEL.relative_to(ROOT)),
        "adapter": str(ADAPTER.relative_to(ROOT)),
        "train_examples": train_count,
        "validation_examples": validation_count,
        "lora": LORA_CONFIG,
        "training": TRAINING_CONFIG,
        "final_progress": last_event,
        "result": result,
        "adapter_bytes": ADAPTER.stat().st_size,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Adapter saved to {ADAPTER}")


def main() -> None:
    for path in (MODEL, TRAIN, VALIDATION, BRIDGE):
        if not path.exists():
            raise FileNotFoundError(path)
    train()


if __name__ == "__main__":
    main()
