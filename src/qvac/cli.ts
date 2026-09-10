import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { createInterface } from "node:readline";

import {
  closeQvac,
  analyzeConversation,
  diarizeAudio,
  extractClinicalEvents,
  indexRag,
  listRagWorkspaces,
  parseDiarization,
  preloadCoreModels,
  searchRag,
  resetPulsoRag,
  synthesize,
  transcribeAudio,
  translateText,
} from "./engine.js";

type ServerRequest = {
  command: string;
  options?: Record<string, unknown>;
};

async function execute(command: string, options: Record<string, unknown>): Promise<unknown> {
  const value = (name: string, fallback?: unknown) => options[name] ?? fallback;
  if (command === "warmup") return preloadCoreModels();
  if (command === "health") {
    const paths = [
      "models/clinical/medpsy-1.7b-q8_0.gguf",
      "training/output/pulso-medpsy-lora.gguf",
      "models/speech/whisper-small-q8_0.bin",
      "models/speech/sortformer-4spk-v2.1-q4_0.gguf",
      "models/embeddings/embeddinggemma-300m-q4_0.gguf",
      "models/speech/supertonic3-q4_0.gguf",
    ];
    return {
      local_only: true,
      files: Object.fromEntries(paths.map((path) => [path, existsSync(resolve(path))])),
    };
  }
  if (command === "extract") return extractClinicalEvents(value("input_json") as Parameters<typeof extractClinicalEvents>[0]);
  if (command === "transcribe") return transcribeAudio(String(value("audio")));
  if (command === "diarize") {
    const raw = await diarizeAudio(String(value("audio")));
    return { segments: parseDiarization(raw), raw };
  }
  if (command === "audio-pipeline") return analyzeConversation(String(value("audio")));
  if (command === "translate") {
    const target = String(value("target", "es"));
    return {
      translated_text: await translateText(String(value("text")), String(value("source")), target),
      target,
    };
  }
  if (command === "rag-index") return indexRag(String(value("corpus", "data/rag/index/corpus.jsonl")));
  if (command === "rag-workspaces") return { workspaces: await listRagWorkspaces() };
  if (command === "rag-reset") return resetPulsoRag();
  if (command === "rag-search") {
    const results = await searchRag(
      String(value("query")),
      String(value("workspace", "pulso-clinical")),
      Number(value("top_k", 5)),
    );
    return { results };
  }
  if (command === "tts") {
    const output = String(value("output"));
    await synthesize(String(value("text")), output, String(value("language", "es")));
    return { output: resolve(output) };
  }
  throw new Error(`Unknown QVAC command: ${command}`);
}

async function serve(): Promise<void> {
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of lines) {
    if (!line.trim()) continue;
    try {
      const request = JSON.parse(line) as ServerRequest;
      const data = await execute(request.command, request.options ?? {});
      process.stdout.write(`__PULSO__${JSON.stringify({ ok: true, data })}\n`);
    } catch (error) {
      process.stdout.write(
        `__PULSO__${JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) })}\n`,
      );
    }
  }
}

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
  throw new Error("Use health, extract, transcribe, diarize, audio-pipeline, translate, rag-index, rag-search, rag-workspaces, rag-reset, or tts.");
}

if (process.argv[2] === "server") {
  try {
    await serve();
  } finally {
    await closeQvac();
  }
} else {
  try {
    await run();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  } finally {
    await closeQvac();
  }
}
