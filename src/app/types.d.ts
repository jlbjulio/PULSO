interface Window {
  pulso: {
    request<T>(payload: Record<string, unknown>): Promise<T>;
    pickDocument(): Promise<string | null>;
    saveRecording(bytes: Uint8Array, extension: string): Promise<string>;
    saveDemoDocument(bytes: Uint8Array): Promise<string>;
    readRuntimeAudio(path: string): Promise<Uint8Array>;
  };
}
