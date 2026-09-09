export type PerformanceRecord = {
  timestamp: string;
  model: string;
  quantization: string;
  task: string;
  prompt: string;
  input_tokens: number;
  output_tokens: number;
  model_load_ms: number;
  ttft_ms: number;
  total_inference_ms: number;
  tokens_per_second: number;
  success: boolean;
  error: string | null;
};

export type ExtractedEvent = {
  event_id: string;
  type: string;
  state: string;
  actor_role: string;
  patient_ref: string | null;
  evidence_utterance_ids: string[];
  payload: Record<string, unknown>;
  actionable: boolean;
  confirmation_required: boolean;
  missing_fields: string[];
  rag_required: boolean;
  supersedes_event_id?: string | null;
};

export type ExtractionResult = {
  events: ExtractedEvent[];
  ignored_utterance_ids: string[];
  session_flags: string[];
};

