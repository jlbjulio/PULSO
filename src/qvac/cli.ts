import { existsSync } from "node:fs";
import { resolve } from "node:path";

import {
  closeQvac,
  analyzeConversation,
  diarizeAudio,
  extractClinicalEvents,
  indexRag,
  listRagWorkspaces,
  parseDiarization,
  readDocument,
  readDocuments,
  searchRag,
  resetPulsoRag,
  synthesize,
  transcribeAudio,
  translateText,
} from "./engine.js";

function option(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function required(name: string): string {
  const value = option(name);
  if (!value) throw new Error(`Missing required option ${name}`);
  return value;
}

async function run(): Promise<void> {
  const command = process.argv[2];
  if (command === "health") {
    const paths = [
      "models/clinical/medpsy-1.7b-q8_0.gguf",
      "training/output/pulso-medpsy-lora.gguf",
      "models/speech/whisper-small-q8_0.bin",
      "models/speech/sortformer-4spk-v2.1-q4_0.gguf",
      "models/ocr/latin-g2.gguf",
      "models/embeddings/embeddinggemma-300m-q4_0.gguf",
      "models/speech/supertonic3-q4_0.gguf",
    ];
    process.stdout.write(`${JSON.stringify({ local_only: true, files: Object.fromEntries(paths.map((path) => [path, existsSync(resolve(path))])) })}\n`);
    return;
  }
  if (command === "extract") {
    const result = await extractClinicalEvents(JSON.parse(required("--input-json")) as Parameters<typeof extractClinicalEvents>[0]);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return;
  }
  if (command === "transcribe") {
    process.stdout.write(`${JSON.stringify(await transcribeAudio(required("--audio")))}\n`);
    return;
  }
  if (command === "diarize") {
    const raw = await diarizeAudio(required("--audio"));
    process.stdout.write(`${JSON.stringify({ segments: parseDiarization(raw), raw })}\n`);
    return;
  }
  if (command === "audio-pipeline") {
    process.stdout.write(`${JSON.stringify(await analyzeConversation(required("--audio")))}\n`);
    return;
  }
  if (command === "translate") {
    const target = option("--target") ?? "es";
    const translatedText = await translateText(required("--text"), required("--source"), target);
    process.stdout.write(`${JSON.stringify({ translated_text: translatedText, target })}\n`);
    return;
  }
  if (command === "ocr") {
    process.stdout.write(`${JSON.stringify(await readDocument(required("--image")))}\n`);
    return;
  }
  if (command === "ocr-batch") {
    const images = JSON.parse(required("--images-json")) as string[];
    process.stdout.write(`${JSON.stringify(await readDocuments(images))}\n`);
    return;
  }
  if (command === "rag-index") {
    const corpus = option("--corpus") ?? "data/rag/index/corpus.jsonl";
    process.stdout.write(`${JSON.stringify(await indexRag(corpus))}\n`);
    return;
  }
  if (command === "rag-workspaces") {
    process.stdout.write(`${JSON.stringify({ workspaces: await listRagWorkspaces() })}\n`);
    return;
  }
  if (command === "rag-reset") {
    process.stdout.write(`${JSON.stringify(await resetPulsoRag())}\n`);
    return;
  }
  if (command === "rag-search") {
    const results = await searchRag(required("--query"), option("--workspace") ?? "pulso-clinical", Number(option("--top-k") ?? 5));
    process.stdout.write(`${JSON.stringify({ results })}\n`);
    return;
  }
  if (command === "tts") {
    await synthesize(required("--text"), required("--output"), option("--language") ?? "es");
    process.stdout.write(`${JSON.stringify({ output: resolve(required("--output")) })}\n`);
    return;
  }
  throw new Error("Use health, extract, transcribe, diarize, audio-pipeline, translate, ocr, ocr-batch, rag-index, rag-search, rag-workspaces, rag-reset, or tts.");
}

try {
  await run();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
} finally {
  await closeQvac();
}
