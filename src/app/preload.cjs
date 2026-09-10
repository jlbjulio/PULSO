const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pulso", {
  request: (payload) => ipcRenderer.invoke("pulso:request", payload),
  saveRecording: (bytes) => ipcRenderer.invoke("pulso:save-recording", bytes),
  readRuntimeAudio: (path) => ipcRenderer.invoke("pulso:read-runtime-audio", path),
  showExport: (path) => ipcRenderer.invoke("pulso:show-export", path),
});
