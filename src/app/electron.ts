import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, dialog, ipcMain, session, shell } from "electron";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(currentDirectory, "../..");

let bridge: ChildProcessWithoutNullStreams | null = null;
let bridgeError = "";
let activeResponse:
  | { resolve: (value: unknown) => void; reject: (reason: Error) => void }
  | undefined;
let requestQueue: Promise<unknown> = Promise.resolve();

function startBridge(): ChildProcessWithoutNullStreams {
  if (bridge && bridge.exitCode === null) return bridge;
  bridgeError = "";
  bridge = spawn("python", ["-u", "-m", "pulso.desktop_bridge"], {
    cwd: projectRoot,
    windowsHide: true,
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
  });
  bridge.stderr.setEncoding("utf8");
  bridge.stderr.on("data", (chunk: string) => {
    bridgeError = `${bridgeError}${chunk}`.slice(-5000);
  });
  createInterface({ input: bridge.stdout, crlfDelay: Infinity }).on("line", (line) => {
    const waiting = activeResponse;
    activeResponse = undefined;
    if (!waiting) return;
    try {
      const response = JSON.parse(line) as { ok: boolean; data?: unknown; error?: string };
      if (!response.ok) throw new Error(response.error || "La operación no pudo completarse");
      waiting.resolve(response.data);
    } catch (error) {
      waiting.reject(error instanceof Error ? error : new Error(String(error)));
    }
  });
  bridge.on("exit", (code) => {
    activeResponse?.reject(
      new Error(bridgeError.trim() || `El motor de PULSO finalizó con código ${code}`),
    );
    activeResponse = undefined;
    bridge = null;
  });
  return bridge;
}

function sendRequest(payload: unknown): Promise<unknown> {
  return new Promise((resolveRequest, rejectRequest) => {
    const process = startBridge();
    activeResponse = { resolve: resolveRequest, reject: rejectRequest };
    process.stdin.write(`${JSON.stringify(payload)}\n`, "utf8", (error) => {
      if (error) {
        activeResponse = undefined;
        rejectRequest(error);
      }
    });
  });
}

function pythonRequest(payload: unknown): Promise<unknown> {
  const next = requestQueue.catch(() => undefined).then(() => sendRequest(payload));
  requestQueue = next;
  return next;
}

async function createWindow(): Promise<void> {
  const window = new BrowserWindow({
    width: 1540,
    height: 960,
    minWidth: 900,
    minHeight: 620,
    backgroundColor: "#07110f",
    titleBarStyle: "hiddenInset",
    show: false,
    webPreferences: {
      preload: join(projectRoot, "src", "app", "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.once("ready-to-show", () => window.show());
  const developmentUrl = process.env.VITE_DEV_SERVER_URL;
  if (developmentUrl) await window.loadURL(developmentUrl);
  else await window.loadFile(join(projectRoot, "dist", "renderer", "index.html"));
}

ipcMain.handle("pulso:request", (_, payload: unknown) => pythonRequest(payload));
ipcMain.handle("pulso:save-recording", async (_, bytes: Uint8Array) => {
  const directory = join(projectRoot, "runtime-data", "recordings");
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${randomUUID()}.wav`);
  await writeFile(path, Buffer.from(bytes));
  return path;
});
ipcMain.handle("pulso:read-runtime-audio", async (_, requestedPath: string) => {
  const runtimeRoot = resolve(projectRoot, "runtime-data");
  const path = resolve(requestedPath);
  if (!path.startsWith(`${runtimeRoot}\\`)) throw new Error("Ruta de audio no autorizada");
  return new Uint8Array(await readFile(path));
});
ipcMain.handle("pulso:show-export", (_, requestedPath: string) => {
  const exportRoot = resolve(projectRoot, "runtime-data", "exports");
  const path = resolve(requestedPath);
  if (!path.startsWith(`${exportRoot}\\`)) throw new Error("Ruta de exportación no autorizada");
  shell.showItemInFolder(path);
});

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_, permission, callback) => {
    callback(permission === "media");
  });
  try {
    await pythonRequest({ action: "initialize", demo: false, warmup: true });
    await createWindow();
  } catch (error) {
    dialog.showErrorBox(
      "PULSO no pudo iniciar",
      error instanceof Error ? error.message : String(error),
    );
    app.quit();
  }
});
app.on("before-quit", () => {
  bridge?.stdin.end();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
