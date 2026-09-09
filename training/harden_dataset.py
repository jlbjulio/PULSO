"""Make the synthetic SFT corpus consistent with PULSO's closed-loop safety contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "finetuning"
ORDER_TYPES = {
    "medication_order",
    "procedure_order",
    "lab_order",
    "imaging_order",
    "consult_order",
    "transfer",
}
SYSTEM = (
    "Extract clinical events from the supplied emergency-room utterances. Return JSON only. "
    "Preserve the distinction between considered, planned, confirmed, administered, completed, "
    "cancelled, denied, and unknown. Never invent a diagnosis, dose, route, result, "
    "actor, or action. "
    "An order is actionable by PULSO only when its evidence begins with the wake word 'Pulso'. "
    "An actionable order always remains pending_confirmation until the clinician reviews "
    "and signs it. "
    "Bedside closed-loop statements may document a confirmed clinical order but are not actionable "
    "by the application without the wake word. Mentioning a medication never proves administration."
)


def wake_case(case_id: str, event_id: str) -> bool:
    digest = hashlib.sha256(f"{case_id}:{event_id}".encode()).digest()
    return digest[0] % 2 == 0


def harden(row: dict) -> dict:
    messages = row["messages"]
    user = json.loads(messages[1]["content"])
    output = json.loads(messages[2]["content"])
    utterances = {item["id"]: item for item in user["utterances"]}
    for event in output["events"]:
        if event["type"] == "code_event":
            event["actionable"] = False
            event["confirmation_required"] = False
            continue
        if event["type"] not in ORDER_TYPES:
            event["actionable"] = False
            event["confirmation_required"] = False
            continue
        evidence = [utterances[item] for item in event["evidence_utterance_ids"]]
        already_wake = any(
            item["text"].casefold().lstrip().startswith("pulso") for item in evidence
        )
        should_wake = event["state"] == "pending_confirmation" and wake_case(
            user["case_id"], event["event_id"]
        )
        if should_wake and not already_wake:
            candidate = next(
                (item for item in evidence if item["speaker"] in {"physician", "nurse"}),
                evidence[0],
            )
            candidate["text"] = f"Pulso, {candidate['text'][0].lower()}{candidate['text'][1:]}"
            already_wake = True
        if already_wake:
            event["actionable"] = True
            event["confirmation_required"] = True
            event["state"] = "pending_confirmation"
        else:
            event["actionable"] = False
            event["confirmation_required"] = False
            if event["state"] == "pending_confirmation":
                event["state"] = "considered"
    messages[0]["content"] = SYSTEM
    messages[1]["content"] = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
    messages[2]["content"] = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    return row


def main() -> None:
    counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        path = DATA / f"{split}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        rows = [harden(row) for row in rows]
        path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        counts[split] = len(rows)
    print(json.dumps({"hardened": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
