const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pulso", {
  request: (payload) => ipcRenderer.invoke("pulso:request", payload),
  pickDocument: () => ipcRenderer.invoke("pulso:pick-document"),
  saveRecording: (bytes, extension) =>
    ipcRenderer.invoke("pulso:save-recording", bytes, extension),
  saveDemoDocument: (bytes) => ipcRenderer.invoke("pulso:save-demo-document", bytes),
  readRuntimeAudio: (path) => ipcRenderer.invoke("pulso:read-runtime-audio", path),
});
