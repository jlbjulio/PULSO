import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { arch, platform } from "node:os";
import { resolve } from "node:path";

import {
  close,
  completion,
  loadModel,
  ragIngest,
  ragListWorkspaces,
  ragCloseWorkspace,
  ragDeleteWorkspace,
  ragReindex,
  ragSearch,
  textToSpeech,
  transcribe,
  translate,
  unloadModel,
  type LoadModelOptions,
} from "@qvac/sdk";

import { writeMetric } from "./metrics.js";
import { normalizeExtraction } from "./normalize.js";
import type { ExtractionResult, PerformanceRecord } from "./types.js";

type ModelSpec = {
  path?: string;
  lora_path?: string;
  vad_path?: string;
  euro?: string;
  quantization?: string;
  qvac_model_type: string;
  model_config?: Record<string, unknown>;
  euro_languages?: string[];
};

type PulsoConfig = {
  runtime: { allow_cloud_inference: boolean };
  models: Record<string, ModelSpec>;
};

const root = resolve(import.meta.dirname, "../..");
const config = JSON.parse(
  await readFile(resolve(root, "config/models.json"), "utf8"),
) as PulsoConfig;
const extractionSchema = JSON.parse(
  await readFile(resolve(root, "schemas/clinical-events.schema.json"), "utf8"),
) as Record<string, unknown>;

const loadedModels = new Map<string, Promise<string>>();
const ragCache = new Map<string, unknown>();
const RAG_CACHE_LIMIT = 128;

if (config.runtime.allow_cloud_inference) {
  throw new Error("PULSO refuses to start when cloud inference is enabled.");
}

const systemPrompt = `You are PULSO's clinical evidence extraction component.
Extract only clinically relevant facts explicitly supported by the supplied utterances.
Use reference_context only to normalize terminology and check workflow consistency; never copy it into the patient record as evidence.
Preserve speaker, patient reference, evidence utterance IDs, uncertainty, corrections, and temporal state.
Thinking aloud or suggesting an option is considered, never ordered.
Only an explicit command clause beginning with the wake word PULSO may be actionable, and it still requires confirmation.
Requests for a named clinical team, specialist, technical service, psychology, psychiatry, social work, transport, or logistical support are consult_order events.
Code Blue and explicit critical-response activations are code_event events.
Mentioning a medication is not administration. Administration requires an explicit statement that it was given.
Never diagnose, prescribe, infer a dose, fill a missing field, or create an action from background speech.
Return at most one event for each distinct fact and never duplicate an event.
Write every payload value in English, even when the source utterance was spoken in another language.
Never include truncation markers such as [incomplete], [truncated], or unfinished transcript fragments.
Return only JSON that satisfies the schema.`;

function localPath(path: string): string {
  return resolve(root, path);
}

function cachedModel(
  key: string,
  options: LoadModelOptions,
): Promise<string> {
  const existing = loadedModels.get(key);
  if (existing) return existing;
  const pending = loadModel(options).catch((error) => {
    loadedModels.delete(key);
    throw error;
  });
  loadedModels.set(key, pending);
  return pending;
}

async function clinicalModel(): Promise<string> {
  const spec = config.models.clinical_extraction;
  if (!spec.path) throw new Error("clinical extraction model path is missing");
  if (!spec.lora_path) throw new Error("PULSO LoRA adapter path is missing");
  const adapterPath = localPath(spec.lora_path);
  if (!existsSync(adapterPath))
    throw new Error("PULSO LoRA adapter is missing; run npm run train first");
  return cachedModel("clinical", {
    modelSrc: localPath(spec.path),
    modelType: "llamacpp-completion",
    modelConfig: {
      ctx_size: 4096,
      gpu_layers: 22,
      lora: adapterPath,
    } as never,
  });
}

async function transcriptionModel(): Promise<string> {
  const spec = config.models.transcription;
  if (!spec.path || !spec.vad_path)
    throw new Error("transcription paths are missing");
  return cachedModel("transcription", {
    modelSrc: localPath(spec.path),
    modelType: "whispercpp-transcription",
    modelConfig: { language: "auto", vadModelSrc: localPath(spec.vad_path) },
  });
}

async function diarizationModel(): Promise<string> {
  const spec = config.models.speaker_diarization;
  if (!spec.path) throw new Error("diarization model path is missing");
  return cachedModel("diarization", {
    modelSrc: localPath(spec.path),
    modelType: "parakeet-transcription",
  });
}

async function embeddingModel(): Promise<string> {
  const spec = config.models.rag_embeddings;
  if (!spec.path) throw new Error("embedding model path is missing");
  return cachedModel("rag", {
    modelSrc: localPath(spec.path),
    modelType: "llamacpp-embedding",
  });
}

async function translationModel(from: string, to: string): Promise<string> {
  const direction = from === "en" ? "en-xx" : "xx-en";
  const files = translationFiles(direction);
  return cachedModel(`translation:${direction}`, {
    modelSrc: files.model,
    modelType: "nmtcpp-translation",
    modelConfig: {
      engine: "Bergamot",
      from,
      to,
      srcVocabSrc: files.vocab,
      dstVocabSrc: files.vocab,
    } as never,
  });
}

async function speechModel(language = "es"): Promise<string> {
  const spec = config.models.speech;
  if (!spec.path) throw new Error("speech model path is missing");
  return cachedModel(`speech:${language}`, {
    modelSrc: localPath(spec.path),
    modelType: "tts-ggml",
    modelConfig: {
      ...spec.model_config,
      language,
      voice: "F1",
      ttsSpeed: 1.08,
      ttsNumInferenceSteps: 5,
    },
  });
}

export async function preloadCoreModels(): Promise<{ loaded: string[] }> {
  const preload = async (
    name: string,
    quantization: string,
    loader: () => Promise<string>,
  ) => {
    const record = metric(name, quantization, "model-preload", "application-startup");
    const started = performance.now();
    try {
      await loader();
      record.model_load_ms = performance.now() - started;
      record.total_inference_ms = record.model_load_ms;
      record.success = true;
    } catch (error) {
      record.error = errorMessage(error);
      throw error;
    } finally {
      await writeMetric(record);
    }
  };
  await preload("MedPsy-1.7B", "Q8_0", clinicalModel);
  await Promise.all([
    preload("Whisper Small", "Q8_0", transcriptionModel),
    preload("Sortformer 4SPK", "Q4_0", diarizationModel),
    preload("EmbeddingGemma 300M", "Q4_0", embeddingModel),
  ]);
  return {
    loaded: [
      "MedPsy",
      "Whisper",
      "Sortformer",
      "EmbeddingGemma",
    ],
  };
}

function metric(
  model: string,
  quantization: string,
  task: string,
  prompt: string,
): PerformanceRecord {
  return {
    timestamp: new Date().toISOString(),
    model,
    quantization,
    task,
    prompt,
    input_tokens: 0,
    output_tokens: 0,
    model_load_ms: 0,
    ttft_ms: 0,
    total_inference_ms: 0,
    tokens_per_second: 0,
    success: false,
    error: null,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function extractClinicalEvents(input: {
  patient_ref: string;
  utterances: Array<{
    id: string;
    speaker: string;
    language: string;
    text: string;
  }>;
  reference_context?: Array<{ content?: string; text?: string; metadata?: unknown }>;
}): Promise<ExtractionResult> {
  const spec = config.models.clinical_extraction;
  if (!spec.path) throw new Error("clinical extraction model path is missing");
  const prompt = JSON.stringify(input);
  const record = metric(
    spec.path,
    spec.quantization ?? "Q4_K_M",
    "clinical-extraction",
    prompt,
  );
  const loadStarted = performance.now();
  try {
    const modelId = await clinicalModel();
    record.model_load_ms = performance.now() - loadStarted;
    const started = performance.now();
    const run = completion({
      modelId,
      history: [
        { role: "system", content: systemPrompt },
        { role: "user", content: prompt },
      ],
      stream: true,
      captureThinking: true,
      generationParams: {
        temp: 0,
        top_p: 0.9,
        predict: 700,
        seed: 42,
        reasoning_budget: 0,
        remove_thinking_from_context: true,
      },
      responseFormat: {
        type: "json_schema",
        json_schema: {
          name: "pulso_clinical_events",
          schema: extractionSchema,
          strict: true,
        },
      },
    });
    const final = await run.final;
    record.total_inference_ms = performance.now() - started;
    record.input_tokens = final.stats?.promptTokens ?? 0;
    record.output_tokens = final.stats?.generatedTokens ?? 0;
    record.ttft_ms = final.stats?.timeToFirstToken ?? 0;
    record.tokens_per_second = final.stats?.tokensPerSecond ?? 0;
    const text = final.contentText.trim() || final.raw.fullText.trim();
    if (!text) throw new Error("MedPsy returned an empty response");
    const parsed = normalizeExtraction(
      JSON.parse(text) as ExtractionResult,
      input,
    );
    record.success = true;
    return parsed;
  } catch (error) {
    record.error = errorMessage(error);
    throw error;
  } finally {
    await writeMetric(record);
  }
}

export async function transcribeAudio(audioPath: string): Promise<unknown> {
  const spec = config.models.transcription;
  if (!spec.path || !spec.vad_path)
    throw new Error("transcription paths are missing");
  const record = metric(spec.path, "Q8_0", "transcription", audioPath);
  const loadStarted = performance.now();
  try {
    const modelId = await transcriptionModel();
    record.model_load_ms = performance.now() - loadStarted;
    const started = performance.now();
    const segments = await transcribe({
      modelId,
      audioChunk: resolve(audioPath),
      metadata: true,
    });
    record.total_inference_ms = performance.now() - started;
    record.success = true;
    return {
      text: segments
        .map((item) => item.text)
        .join(" ")
        .trim(),
      segments,
    };
  } catch (error) {
    record.error = errorMessage(error);
    throw error;
  } finally {
    await writeMetric(record);
  }
}

export async function diarizeAudio(audioPath: string): Promise<string> {
  const spec = config.models.speaker_diarization;
  if (!spec.path) throw new Error("diarization model path is missing");
  const modelId = await diarizationModel();
  return await transcribe({ modelId, audioChunk: resolve(audioPath) });
}

function seconds(value: string): number {
  return value
    .split(":")
    .map(Number)
    .reduce((total, part) => total * 60 + part, 0);
}

export function parseDiarization(raw: string) {
  const segments = raw
    .split(/\r?\n/)
    .map((line) =>
      line.match(/Speaker\s+(\d+)\s*:\s*([\d.:]+)s?\s*-\s*([\d.:]+)s?/i),
    )
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => ({
      speaker: Number(match[1]),
      startMs: seconds(match[2]) * 1000,
      endMs: seconds(match[3]) * 1000,
    }));
  return segments.sort((left, right) => left.startMs - right.startMs);
}

export async function analyzeConversation(audioPath: string): Promise<unknown> {
  const [transcript, diarizationRaw] = await Promise.all([
    transcribeAudio(audioPath),
    diarizeAudio(audioPath),
  ]);
  const typed = transcript as {
    text: string;
    segments: Array<{
      text: string;
      startMs: number;
      endMs: number;
      id?: string;
    }>;
  };
  const speakers = parseDiarization(diarizationRaw);
  const utterances = typed.segments.map((segment, index) => {
    const match = speakers
      .map((speaker) => ({
        speaker,
        overlap: Math.max(
          0,
          Math.min(segment.endMs, speaker.endMs) -
            Math.max(segment.startMs, speaker.startMs),
        ),
      }))
      .sort((left, right) => right.overlap - left.overlap)[0];
    return {
      id: segment.id === undefined ? `audio-${index + 1}` : String(segment.id),
      speaker:
        match && match.overlap > 0 ? `speaker_${match.speaker}` : "unknown",
      text: segment.text.trim(),
      start_ms: segment.startMs,
      end_ms: segment.endMs,
    };
  });
  return { text: typed.text, utterances, diarization: speakers };
}

function translationFiles(direction: "xx-en" | "en-xx") {
  const spec = config.models.translation;
  const base = spec.euro;
  if (!base) throw new Error("translation model path is missing");
  const directory = `${base}/${direction}/Base/intgemm`;
  return {
    model: localPath(`${directory}/model.intgemm.alphas.bin`),
    vocab: localPath(`${directory}/vocab.spm`),
  };
}

async function translateStep(
  text: string,
  from: string,
  to: string,
): Promise<string> {
  const taggedText = tagTranslationInput(text, from, to);
  const modelId = await translationModel(from, to);
  return await translate({
    modelId,
    text: taggedText,
    modelType: "nmtcpp-translation",
    stream: false,
  }).text.then((result) => result.trim());
}

export function tagTranslationInput(
  text: string,
  from: string,
  to: string,
): string {
  return from === "en" ? `##${to.toUpperCase()} ${text}` : text;
}

export async function translateText(
  text: string,
  source: string,
  target: string,
): Promise<string> {
  if (source === target) return text;
  const translation = config.models.translation;
  const supported = new Set(["en", ...(translation.euro_languages ?? [])]);
  if (!supported.has(source) || !supported.has(target)) {
    throw new Error(`unsupported local translation pair: ${source}-${target}`);
  }
  const english =
    source === "en" ? text : await translateStep(text, source, "en");
  return target === "en" ? english : translateStep(english, "en", target);
}

export async function indexRag(corpusPath: string): Promise<unknown> {
  const spec = config.models.rag_embeddings;
  if (!spec.path) throw new Error("embedding model path is missing");
  const lines = (await readFile(resolve(corpusPath), "utf8"))
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { workspace: string; content: string });
  let modelId: string | undefined;
  const counts: Record<string, number> = {};
  try {
    modelId = await loadModel({
      modelSrc: localPath(spec.path),
      modelType: "llamacpp-embedding",
    });
    for (const workspace of [...new Set(lines.map((line) => line.workspace))]) {
      const documents = lines
        .filter((line) => line.workspace === workspace)
        .map((line) => line.content);
      const result = await ragIngest({
        modelId,
        workspace,
        documents,
        chunk: false,
      });
      counts[workspace] = result.processed.length;
      await ragReindex({ workspace });
    }
    return { indexed: counts };
  } finally {
    if (modelId) await unloadModel({ modelId });
  }
}

export async function searchRag(
  query: string,
  workspace: string,
  topK: number,
): Promise<unknown> {
  const spec = config.models.rag_embeddings;
  if (!spec.path) throw new Error("embedding model path is missing");
  const cacheKey = `${workspace}:${topK}:${query.trim().toLocaleLowerCase()}`;
  const cached = ragCache.get(cacheKey);
  if (cached) return cached;
  const modelId = await embeddingModel();
  const results = await ragSearch({ modelId, workspace, query, topK, n: 3 });
  if (ragCache.size >= RAG_CACHE_LIMIT) {
    ragCache.delete(ragCache.keys().next().value as string);
  }
  ragCache.set(cacheKey, results);
  return results;
}

export async function listRagWorkspaces(): Promise<unknown> {
  return ragListWorkspaces();
}

export async function resetPulsoRag(): Promise<unknown> {
  ragCache.clear();
  const existing = await ragListWorkspaces();
  const names = existing
    .map((item) => item.name)
    .filter((name) => name.startsWith("pulso-"));
  for (const workspace of names) {
    const info = existing.find((item) => item.name === workspace);
    if (info?.open) await ragCloseWorkspace({ workspace });
    await ragDeleteWorkspace({ workspace });
  }
  return { deleted: names };
}

function wavHeader(dataLength: number, sampleRate: number): Buffer {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataLength, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataLength, 40);
  return header;
}

export async function synthesize(
  text: string,
  outputPath: string,
  language = "es",
): Promise<void> {
  const modelId = await speechModel(language);
  const samples = await textToSpeech({
    modelId,
    text,
    inputType: "text",
    stream: false,
  }).buffer;
  const pcm = Buffer.alloc(samples.length * 2);
  samples.forEach((sample, index) =>
    pcm.writeInt16LE(Math.max(-32768, Math.min(32767, sample)), index * 2),
  );
  await writeFile(
    resolve(outputPath),
    Buffer.concat([wavHeader(pcm.length, 44100), pcm]),
  );
}

export async function closeQvac(): Promise<void> {
  const ids = await Promise.allSettled(loadedModels.values());
  for (const item of ids) {
    if (item.status === "fulfilled") await unloadModel({ modelId: item.value });
  }
  loadedModels.clear();
  await close();
}

export function runtimeIdentity(): string {
  return `${platform()}-${arch()}`;
}
