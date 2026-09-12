# PULSO

PULSO is a local clinical operations copilot for emergency departments. It follows the encounter in real time, preserves clinically relevant facts, bridges language barriers, and coordinates voice-initiated orders through professional review and closed-loop confirmation.

## How it works

1. A clinician starts an encounter for a treatment bay. PULSO assigns a temporary patient reference that can be updated after identification.
2. Whisper transcribes short audio windows while Sortformer separates speakers. The full conversation remains visible during the encounter, independently from the clinical event record.
3. If the patient speaks another supported language, TranslatePsy translates the patient into Spanish and the clinician into the patient's language. Supertonic can play either translation on demand.
4. For medication, orders, critical activations, transfers, and workflow events, local RAG retrieves a small amount of relevant emergency, safety, or interoperability context. MedPsy uses it to normalize terminology and validate structure without treating reference material as patient evidence.
5. MedPsy with PULSO's LoRA adapter extracts symptoms, history, vital signs, findings, documented assessments, interventions, results, and orders.
6. Only an explicit instruction beginning with the `Pulso` wake word can create an order. Every order must be reviewed and signed by a clinician before dispatch.
7. Closing the encounter produces a formatted Word report containing relevant clinical facts, orders, timeline, identity, and signature, plus a FHIR R4 bundle.

The desktop app includes synthetic walkthroughs and an on-demand microphone demo. Normal operation uses continuous listening.

## Architecture

- `src/app/`: Electron and React desktop application.
- `src/pulso/clinical/`: encounters, events, safety gates, orders, and reports.
- `src/pulso/storage/`: SQLite persistence, audit chain, routing, and local queue.
- `src/pulso/ai/`: audio, translation, retrieval, and clinical extraction services.
- `src/qvac/`: local inference through `@qvac/sdk`.
- `training/`: LoRA training and evaluation.
- `data/`: RAG corpus, evaluation fixtures, and synthetic fine-tuning data.

## Models

| Task | Model |
| --- | --- |
| Clinical extraction | `qvac/MedPsy-1.7B-GGUF`, Q8_0, with the PULSO LoRA adapter |
| Transcription | Whisper Small Q8_0 with Silero VAD 5.1.2 |
| Speaker diarization | Sortformer 4SPK v2.1 Q4_0 |
| Retrieval | EmbeddingGemma 300M Q4_0 |
| Translation | `qvac/TranslatePsy-EuroNano`, INTGEMM |
| Speech synthesis | Supertonic 3 Q4_0 |

MedPsy, Whisper, Sortformer, and EmbeddingGemma are warmed once and reused for the process lifetime. Translation and speech models load on first use and remain cached, avoiding startup work for same-language encounters. The RAG corpus is embedded once during setup, reindexed for faster retrieval, queried only for relevant clinical operations, and served from a bounded in-memory query cache when requests repeat.

Inference and retrieval run locally through QVAC. Performance records—including model load time, token counts, TTFT, latency, and throughput—are written to `runtime-data/performance.jsonl`.

## Installation

Requirements:

- Windows 11
- Python 3.11 or newer
- Node.js 22.17 or newer
- Approximately 12 GB of free disk space

PULSO uses the system Python installation and does not require a virtual environment.

```console
python tools/prepare_environment.py
```

The setup command installs dependencies, downloads the models and public RAG sources, prepares and indexes the corpus, initializes local storage, and validates the project. Start the desktop application with:

```console
npm run app
```

## Fine-tuning

The synthetic SFT dataset teaches the adapter to distinguish facts, negations, corrections, completed actions, considered options, and explicit commands.

```console
npm run train
npm run train:evaluate
```

Training runs locally. TensorBoard is available at `http://127.0.0.1:6006`, and the exported adapter is written to `training/output/pulso-medpsy-lora.gguf`.

## Verification

```console
npm run check
```

Microphone behavior and the complete clinical workflow require a manual test in the desktop application using synthetic data.

## Safety

PULSO is an operational support tool, not a validated medical device. It does not diagnose, prescribe, or execute orders autonomously. A discussed possibility is not recorded as a completed action, and mentioning a medication does not mean it was administered. Orders require explicit intent, clinician review, identity, and signature.

Uncertain output remains subject to professional review. PULSO does not replace clinical judgment, hospital protocols, official emergency channels, or professional interpretation services.

## Data and licenses

Original source code is available under the MIT License. Models, publications, datasets, and third-party components retain their respective licenses. `data/rag/manifest.json` records source URLs, checksums, attribution, licenses, and inclusion status; `data/rag/sources.csv` lists the active corpus.

The corpus contains public material from the World Health Organization, HL7 FHIR definitions, and official Panamanian legal sources. It is indexed locally, and detectable email addresses and phone numbers are removed during preparation.
