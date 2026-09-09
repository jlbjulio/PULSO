import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { completion, loadModel, unloadModel } from "@qvac/sdk";

type Message = { role: "system" | "user" | "assistant"; content: string };
type Case = { messages: Message[] };
type Event = {
  type: string;
  state: string;
  actionable: boolean;
  confirmation_required: boolean;
  evidence_utterance_ids: string[];
};
type Output = { events: Event[]; ignored_utterance_ids: string[]; session_flags: string[] };

const root = resolve(import.meta.dirname, "..");
const model = resolve(root, "models/clinical/medpsy-1.7b-q8_0.gguf");
const adapter = resolve(root, "training/output/pulso-medpsy-lora.gguf");
const testPath = resolve(root, "data/finetuning/test.jsonl");
const outputPath = resolve(root, "benchmarks/medpsy-evaluation.json");
const schema = JSON.parse(
  await readFile(resolve(root, "schemas/clinical-events.schema.json"), "utf8"),
) as Record<string, unknown>;
const limitArg = process.argv.find((item) => item.startsWith("--limit="));
const limit = limitArg ? Number(limitArg.split("=")[1]) : Number.POSITIVE_INFINITY;
const cases = (await readFile(testPath, "utf8"))
  .split(/\r?\n/)
  .filter(Boolean)
  .slice(0, limit)
  .map((line) => JSON.parse(line) as Case);

function eventSignature(event: Event): string {
  return JSON.stringify({
    type: event.type,
    state: event.state,
    actionable: event.actionable,
    confirmation_required: event.confirmation_required,
    evidence_utterance_ids: [...event.evidence_utterance_ids].sort(),
  });
}

let modelId: string | undefined;
try {
  modelId = await loadModel({
    modelSrc: model,
    modelType: "llamacpp-completion",
    modelConfig: { ctx_size: 2048, gpu_layers: 22, lora: adapter },
  });
  const details: Array<Record<string, unknown>> = [];
  let valid = 0;
  let matchedEvents = 0;
  let expectedEvents = 0;
  for (const [index, item] of cases.entries()) {
    const expected = JSON.parse(item.messages[2].content) as Output;
    expectedEvents += expected.events.length;
    const started = performance.now();
    const run = completion({
      modelId,
      history: item.messages.slice(0, 2),
      stream: true,
      captureThinking: true,
      generationParams: {
        temp: 0,
        seed: 42,
        predict: 1200,
        reasoning_budget: 0,
        remove_thinking_from_context: true,
      },
      responseFormat: {
        type: "json_schema",
        json_schema: { name: "pulso_evaluation", schema, strict: true },
      },
    });
    const final = await run.final;
    let actual: Output | null = null;
    try {
      actual = JSON.parse(final.contentText.trim() || final.raw.fullText.trim()) as Output;
      valid += 1;
      const actualSignatures = new Set(actual.events.map(eventSignature));
      matchedEvents += expected.events.filter((event) => actualSignatures.has(eventSignature(event))).length;
    } catch {
      actual = null;
    }
    details.push({
      case: index + 1,
      prompt: item.messages.slice(0, 2),
      valid_json: actual !== null,
      expected_events: expected.events.length,
      actual_events: actual?.events.length ?? 0,
      matched_events: actual
        ? expected.events.filter((event) => new Set(actual.events.map(eventSignature)).has(eventSignature(event))).length
        : 0,
      elapsed_ms: performance.now() - started,
      input_tokens: final.stats?.promptTokens ?? 0,
      output_tokens: final.stats?.generatedTokens ?? 0,
      ttft_ms: final.stats?.timeToFirstToken ?? 0,
      tokens_per_second: final.stats?.tokensPerSecond ?? 0,
    });
    process.stdout.write(`case=${index + 1}/${cases.length}\n`);
  }
  const report = {
    model: "qvac/MedPsy-1.7B-GGUF",
    quantization: "Q8_0",
    adapter: "training/output/pulso-medpsy-lora.gguf",
    cases: cases.length,
    valid_json_rate: cases.length ? valid / cases.length : 0,
    event_exact_match_recall: expectedEvents ? matchedEvents / expectedEvents : 0,
    details,
  };
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report)}\n`);
} finally {
  if (modelId) await unloadModel({ modelId });
}
