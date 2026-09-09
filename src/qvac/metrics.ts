import { appendFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import type { PerformanceRecord } from "./types.js";

const destination = resolve("runtime-data/performance.jsonl");

export async function writeMetric(metric: PerformanceRecord): Promise<void> {
  await mkdir(dirname(destination), { recursive: true });
  await appendFile(destination, `${JSON.stringify(metric)}\n`, "utf8");
}

