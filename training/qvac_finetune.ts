import { readFile } from "node:fs/promises";

import { finetune, loadModel, unloadModel } from "@qvac/sdk";

type TrainingRequest = {
  modelPath: string;
  trainPath: string;
  validationPath: string;
  adapterPath: string;
  checkpointPath?: string;
  modelConfig: Record<string, unknown>;
  options: Record<string, unknown>;
};

const requestPath = process.argv[2];
if (!requestPath) throw new Error("A training request path is required.");
const request = JSON.parse(await readFile(requestPath, "utf8")) as TrainingRequest;

let modelId: string | undefined;
try {
  modelId = await loadModel({
    modelSrc: request.modelPath,
    modelType: "llamacpp-completion",
    modelConfig: request.modelConfig as never,
  });
  const handle = finetune({
    modelId,
    options: {
      trainDatasetDir: request.trainPath,
      validation: { type: "dataset", path: request.validationPath },
      outputParametersDir: request.adapterPath,
      ...(request.checkpointPath
        ? { checkpointSaveDir: request.checkpointPath }
        : {}),
      ...request.options,
    },
  });
  const progress = (async () => {
    for await (const event of handle.progressStream) {
      process.stdout.write(`PULSO_PROGRESS ${JSON.stringify(event)}\n`);
    }
  })();
  const result = await handle.result;
  await progress;
  process.stdout.write(`PULSO_RESULT ${JSON.stringify(result)}\n`);
} finally {
  if (modelId) await unloadModel({ modelId, clearStorage: false });
}
