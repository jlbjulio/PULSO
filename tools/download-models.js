import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { copyFile, mkdir, readdir, rename, rm, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

import {
  close,
  downloadAsset,
  EMBEDDINGGEMMA_300M_Q4_0,
  OCR_CRAFT,
  OCR_LATIN,
  PARAKEET_SORTFORMER_4SPK_V2_1_Q4_0,
  TTS_MULTILINGUAL_SUPERTONIC3_Q4_0,
  VAD_SILERO_5_1_2,
  WHISPER_SMALL_Q8_0,
} from "@qvac/sdk";

const root = resolve(import.meta.dirname, "..");
const cacheRoot = join(homedir(), ".qvac", "models");

const registryAssets = [
  [WHISPER_SMALL_Q8_0, "models/speech/whisper-small-q8_0.bin"],
  [VAD_SILERO_5_1_2, "models/speech/silero-vad-5.1.2.bin"],
  [
    PARAKEET_SORTFORMER_4SPK_V2_1_Q4_0,
    "models/speech/sortformer-4spk-v2.1-q4_0.gguf",
  ],
  [OCR_CRAFT, "models/ocr/craft-mlt-25k.gguf"],
  [OCR_LATIN, "models/ocr/latin-g2.gguf"],
  [EMBEDDINGGEMMA_300M_Q4_0, "models/embeddings/embeddinggemma-300m-q4_0.gguf"],
  [TTS_MULTILINGUAL_SUPERTONIC3_Q4_0, "models/speech/supertonic3-q4_0.gguf"],
];

const remoteAssets = [
  {
    destination: "models/clinical/medpsy-4b-q4_k_m-imat.gguf",
    url: "https://huggingface.co/qvac/MedPsy-4B-GGUF/resolve/main/medpsy-4b-q4_k_m-imat.gguf",
    size: 2716068640,
    sha256: "2ecbf622a2856f631001f20f593669aa03acba39977f521bef80cd8600864980",
  },
  {
    destination:
      "models/translation/afri/en-xx/Base/intgemm/model.intgemm.alphas.bin",
    url: "https://huggingface.co/qvac/TranslatePsy-AfriNano/resolve/main/en-xx/Base/intgemm/model.intgemm.alphas.bin",
    size: 42993131,
    sha256: "d7f4b4c4399f2f5f782cb67bb67a768151a5989f59b23d74af6d77699a01f453",
  },
  {
    destination: "models/translation/afri/en-xx/Base/intgemm/vocab.spm",
    url: "https://huggingface.co/qvac/TranslatePsy-AfriNano/resolve/main/en-xx/Base/intgemm/vocab.spm",
    size: 800823,
    sha256: "f7e3068abd436998d3e6793dfa0ef55cd23ebb93d64324d9216e7f8e920d77b2",
  },
  {
    destination:
      "models/translation/afri/xx-en/Base/intgemm/model.intgemm.alphas.bin",
    url: "https://huggingface.co/qvac/TranslatePsy-AfriNano/resolve/main/xx-en/Base/intgemm/model.intgemm.alphas.bin",
    size: 42993131,
    sha256: "5af5212975c4b298ac529b1050b94b6c34e82b5ecbc270477bd322285841cb8f",
  },
  {
    destination: "models/translation/afri/xx-en/Base/intgemm/vocab.spm",
    url: "https://huggingface.co/qvac/TranslatePsy-AfriNano/resolve/main/xx-en/Base/intgemm/vocab.spm",
    size: 800386,
    sha256: "32b670fb652a39c843382fa9e4be537c373f7d30479e12332cec158380c0b710",
  },
  {
    destination:
      "models/translation/euro/en-xx/Base/intgemm/model.intgemm.alphas.bin",
    url: "https://huggingface.co/qvac/TranslatePsy-EuroNano/resolve/main/en-xx/Base/intgemm/model.intgemm.alphas.bin",
    size: 42993131,
    sha256: "45f8472add63cc9e00950b4711afb37ac3c6b2bc81f1daff592ab497a4cbb61d",
  },
  {
    destination: "models/translation/euro/en-xx/Base/intgemm/vocab.spm",
    url: "https://huggingface.co/qvac/TranslatePsy-EuroNano/resolve/main/en-xx/Base/intgemm/vocab.spm",
    size: 805236,
    sha256: "167fb634e5e65a0beeef3d1961d6f6d8d2c64b0ac6c6db2017fa4bae63e08239",
  },
  {
    destination:
      "models/translation/euro/xx-en/Base/intgemm/model.intgemm.alphas.bin",
    url: "https://huggingface.co/qvac/TranslatePsy-EuroNano/resolve/main/xx-en/Base/intgemm/model.intgemm.alphas.bin",
    size: 42993131,
    sha256: "50f86c092f4c55055eab7c9052e3c952d38ef601d906d375e6245c0ba129fc2b",
  },
  {
    destination: "models/translation/euro/xx-en/Base/intgemm/vocab.spm",
    url: "https://huggingface.co/qvac/TranslatePsy-EuroNano/resolve/main/xx-en/Base/intgemm/vocab.spm",
    size: 797560,
    sha256: "772276ad54e95628b7ded9a835b6a9eaf08e76b8e754bc57b99bf1cd3d99c138",
  },
];

async function sha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

async function valid(path, size, checksum) {
  try {
    const info = await stat(path);
    return info.size === size && (await sha256(path)) === checksum;
  } catch {
    return false;
  }
}

async function filesBelow(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...(await filesBelow(path)));
    else if (entry.isFile()) found.push(path);
  }
  return found;
}

async function cachedFile(descriptor) {
  const files = await filesBelow(cacheRoot);
  const candidates = files.filter((path) => {
    const name = basename(path);
    return (
      name === descriptor.modelId || name.endsWith(`_${descriptor.modelId}`)
    );
  });
  for (const path of candidates) {
    if (await valid(path, descriptor.expectedSize, descriptor.sha256Checksum))
      return path;
  }
  throw new Error(
    `QVAC descargó ${descriptor.name}, pero no se encontró un archivo válido.`,
  );
}

async function ensureRegistryModel(descriptor, relativeDestination) {
  const destination = resolve(root, relativeDestination);
  if (
    await valid(destination, descriptor.expectedSize, descriptor.sha256Checksum)
  ) {
    console.log(`OK ${relativeDestination}`);
    return;
  }

  let lastPercent = -10;
  await downloadAsset({
    assetSrc: descriptor,
    onProgress(progress) {
      const percent = Math.floor(Number(progress.percentage ?? 0) / 10) * 10;
      if (percent >= lastPercent + 10) {
        lastPercent = percent;
        console.log(`${descriptor.name}: ${percent}%`);
      }
    },
  });

  const source = await cachedFile(descriptor);
  await mkdir(dirname(destination), { recursive: true });
  await copyFile(source, destination);
  if (
    !(await valid(
      destination,
      descriptor.expectedSize,
      descriptor.sha256Checksum,
    ))
  ) {
    throw new Error(`Falló la verificación de ${relativeDestination}.`);
  }
  console.log(`OK ${relativeDestination}`);
}

async function ensureRemoteModel(asset) {
  const destination = resolve(root, asset.destination);
  if (await valid(destination, asset.size, asset.sha256)) {
    console.log(`OK ${asset.destination}`);
    return;
  }

  await mkdir(dirname(destination), { recursive: true });
  const partial = `${destination}.part`;
  let offset = 0;
  try {
    offset = (await stat(partial)).size;
  } catch {
    // No partial download exists.
  }

  const headers = offset > 0 ? { Range: `bytes=${offset}-` } : {};
  let response = await fetch(asset.url, { headers, redirect: "follow" });
  if (response.status === 416) {
    await rm(partial, { force: true });
    offset = 0;
    response = await fetch(asset.url, { redirect: "follow" });
  }
  if (!response.ok || !response.body) {
    throw new Error(
      `No se pudo descargar ${asset.destination}: HTTP ${response.status}`,
    );
  }
  const append = offset > 0 && response.status === 206;
  if (!append) offset = 0;

  let received = offset;
  let lastPercent = -10;
  const source = Readable.fromWeb(response.body);
  source.on("data", (chunk) => {
    received += chunk.length;
    const percent = Math.floor((received / asset.size) * 10) * 10;
    if (percent >= lastPercent + 10) {
      lastPercent = percent;
      console.log(`${asset.destination}: ${Math.min(percent, 100)}%`);
    }
  });
  await pipeline(
    source,
    createWriteStream(partial, { flags: append ? "a" : "w" }),
  );

  if (!(await valid(partial, asset.size, asset.sha256))) {
    throw new Error(`Checksum o tamaño inválido para ${asset.destination}.`);
  }
  await rm(destination, { force: true });
  await rename(partial, destination);
  console.log(`OK ${asset.destination}`);
}

try {
  for (const [descriptor, destination] of registryAssets) {
    await ensureRegistryModel(descriptor, destination);
  }
  for (const asset of remoteAssets) await ensureRemoteModel(asset);
  console.log("Todos los modelos de PULSO están listos.");
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  await close();
}
