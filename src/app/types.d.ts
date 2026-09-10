interface Window {
  pulso: {
    request<T>(payload: Record<string, unknown>): Promise<T>;
    saveRecording(bytes: Uint8Array): Promise<string>;
    readRuntimeAudio(path: string): Promise<Uint8Array>;
    showExport(path: string): Promise<void>;
  };
}
