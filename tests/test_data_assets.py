import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
FINETUNING = ROOT / "data" / "finetuning"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def decoded_case(row: dict) -> tuple[dict, dict]:
    messages = row["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
    return json.loads(messages[1]["content"]), json.loads(messages[2]["content"])


def semantic_signature(row: dict) -> str:
    user, output = decoded_case(row)
    payload = {
        "utterances": [
            {
                "speaker": item["speaker"],
                "language": item["language"],
                "text": item["text"],
            }
            for item in user["utterances"]
        ],
        "output": output,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(serialized).hexdigest()


def test_finetuning_splits_are_valid_and_isolated() -> None:
    manifest = json.loads((FINETUNING / "manifest.json").read_text(encoding="utf-8"))
    seen_case_ids: set[str] = set()
    seen_patient_refs: set[str] = set()
    signatures: dict[str, set[str]] = {}

    for split, expected_count in manifest["splits"].items():
        rows = load_jsonl(FINETUNING / f"{split}.jsonl")
        assert len(rows) == expected_count
        signatures[split] = set()

        for row in rows:
            user, output = decoded_case(row)
            assert user["case_id"] not in seen_case_ids
            assert user["patient_ref"] not in seen_patient_refs
            seen_case_ids.add(user["case_id"])
            seen_patient_refs.add(user["patient_ref"])
            signatures[split].add(semantic_signature(row))

            utterance_ids = {item["id"] for item in user["utterances"]}
            event_ids = {item["event_id"] for item in output["events"]}
            assert len(event_ids) == len(output["events"])
            assert set(output["ignored_utterance_ids"]).issubset(utterance_ids)

            for event in output["events"]:
                assert set(event["evidence_utterance_ids"]).issubset(utterance_ids)
                if event["state"] == "pending_confirmation":
                    assert event["confirmation_required"]
                if event["state"] == "administered":
                    assert event["type"] == "medication_administration"
                if event.get("supersedes_event_id") is not None:
                    assert event["supersedes_event_id"] in event_ids

    assert signatures["train"].isdisjoint(signatures["validation"])
    assert signatures["train"].isdisjoint(signatures["test"])
    assert signatures["validation"].isdisjoint(signatures["test"])


def test_finetuning_covers_every_event_type_and_state() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "clinical-events.schema.json").read_text(encoding="utf-8")
    )
    event_properties = schema["definitions"]["event"]["properties"]
    expected_types = set(event_properties["type"]["enum"])
    expected_states = set(event_properties["state"]["enum"])
    observed_types: set[str] = set()
    observed_states: set[str] = set()

    for split in ("train", "validation", "test"):
        for row in load_jsonl(FINETUNING / f"{split}.jsonl"):
            _, output = decoded_case(row)
            observed_types.update(event["type"] for event in output["events"])
            observed_states.update(event["state"] for event in output["events"])

    assert observed_types == expected_types
    assert observed_states == expected_states


def test_rag_evaluation_references_known_sources() -> None:
    manifest = json.loads((ROOT / "data" / "rag" / "manifest.json").read_text(encoding="utf-8-sig"))
    source_ids = {item["id"] for item in manifest if item.get("include_in_rag", True)}
    cases = load_jsonl(ROOT / "data" / "evaluation" / "rag-retrieval.jsonl")
    case_ids = {item["case_id"] for item in cases}

    assert len(cases) >= 30
    assert len(case_ids) == len(cases)
    for case in cases:
        assert set(case["expected_source_ids"]).issubset(source_ids)
        if case["expected_status"] == "not_applicable":
            assert case["workspace"] is None
            assert not case["expected_source_ids"]
        else:
            assert case["workspace"]
            assert case["expected_source_ids"]


def test_machine_readable_schemas_are_valid_json() -> None:
    for filename in ("clinical-events.schema.json", "rag-verification.schema.json"):
        schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


def test_actionable_training_orders_have_wake_word_and_confirmation_gate() -> None:
    for split in ("train", "validation", "test"):
        for row in load_jsonl(FINETUNING / f"{split}.jsonl"):
            user, output = decoded_case(row)
            utterances = {item["id"]: item["text"] for item in user["utterances"]}
            for event in output["events"]:
                if not event["actionable"]:
                    continue
                evidence = [utterances[item] for item in event["evidence_utterance_ids"]]
                assert any(text.casefold().lstrip().startswith("pulso") for text in evidence)
                assert event["confirmation_required"] is True
                assert event["state"] == "pending_confirmation"


def test_inference_is_restricted_to_local_or_p2p_qvac() -> None:
    config = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))
    assert config["runtime"] == {
        "provider": "qvac",
        "inference_mode": "local_or_p2p",
        "allow_cloud_inference": False,
    }

    for model in config["models"].values():
        for key, value in model.items():
            if isinstance(value, str) and (key.endswith("path") or key in {"euro", "afri"}):
                assert "://" not in value
                assert not Path(value).is_absolute()
