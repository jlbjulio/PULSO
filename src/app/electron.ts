import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

import { app, BrowserWindow, dialog, ipcMain, session } from "electron";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(currentDirectory, "../..");

function pythonRequest(payload: unknown): Promise<unknown> {
  return new Promise((resolveRequest, rejectRequest) => {
    const process = spawn("python", ["-m", "pulso.desktop_bridge"], {
      cwd: projectRoot,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let output = "";
    let errors = "";
    process.stdout.setEncoding("utf8");
    process.stderr.setEncoding("utf8");
    process.stdout.on("data", (chunk) => (output += chunk));
    process.stderr.on("data", (chunk) => (errors += chunk));
    process.on("error", rejectRequest);
    process.on("close", (code) => {
      if (code !== 0) {
        rejectRequest(new Error(errors.trim() || `PULSO finalizó con código ${code}`));
        return;
      }
      try {
        const response = JSON.parse(output) as { ok: boolean; data?: unknown; error?: string };
        if (!response.ok) throw new Error(response.error || "La operación no pudo completarse");
        resolveRequest(response.data);
      } catch (error) {
        rejectRequest(error);
      }
    });
    process.stdin.end(JSON.stringify(payload));
  });
}

async function createWindow(): Promise<void> {
  const window = new BrowserWindow({
    width: 1540,
    height: 960,
    minWidth: 1180,
    minHeight: 720,
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
ipcMain.handle("pulso:pick-document", async () => {
  const result = await dialog.showOpenDialog({
    title: "Seleccionar documento clínico autorizado",
    properties: ["openFile"],
    filters: [{ name: "Documentos", extensions: ["pdf", "png", "jpg", "jpeg", "bmp"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});
ipcMain.handle("pulso:save-recording", async (_, bytes: Uint8Array, extension: string) => {
  const directory = join(projectRoot, "runtime-data", "recordings");
  await mkdir(directory, { recursive: true });
  const safeExtension = extension === "wav" ? "wav" : "webm";
  const path = join(directory, `${randomUUID()}.${safeExtension}`);
  await writeFile(path, Buffer.from(bytes));
  return path;
});
ipcMain.handle("pulso:save-demo-document", async (_, bytes: Uint8Array) => {
  const directory = join(projectRoot, "runtime-data", "demo-documents");
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${randomUUID()}.png`);
  await writeFile(path, Buffer.from(bytes));
  return path;
});
ipcMain.handle("pulso:read-runtime-audio", async (_, requestedPath: string) => {
  const runtimeRoot = resolve(projectRoot, "runtime-data");
  const path = resolve(requestedPath);
  if (!path.startsWith(`${runtimeRoot}\\`)) throw new Error("Ruta de audio no autorizada");
  return new Uint8Array(await readFile(path));
});

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_, permission, callback) => {
    callback(permission === "media");
  });
  await createWindow();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) void createWindow();
});
