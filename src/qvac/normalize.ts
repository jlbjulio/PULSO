import type { ExtractionResult } from "./types.js";

const orderTypes = new Set([
  "medication_order",
  "procedure_order",
  "lab_order",
  "imaging_order",
  "consult_order",
  "transfer",
]);

export function normalizeExtraction(
  result: ExtractionResult,
  input: { patient_ref: string; utterances: Array<{ id: string }> },
): ExtractionResult {
  const utteranceIds = new Set(input.utterances.map((item) => item.id));
  const eventIds = new Set(result.events.map((item) => item.event_id));
  const events = result.events
    .filter((event) => event.evidence_utterance_ids.every((id) => utteranceIds.has(id)))
    .map((event) => {
      const isOrder = orderTypes.has(event.type);
      const supersedes = event.supersedes_event_id;
      return {
        ...event,
        patient_ref: input.patient_ref,
        actionable: isOrder ? Boolean(event.actionable) : false,
        confirmation_required: isOrder ? Boolean(event.actionable) : false,
        state:
          isOrder && event.actionable ? "pending_confirmation" : event.state,
        supersedes_event_id:
          supersedes && eventIds.has(supersedes) ? supersedes : null,
      };
    });
  return {
    events,
    ignored_utterance_ids: result.ignored_utterance_ids.filter((id) => utteranceIds.has(id)),
    session_flags: [...new Set(result.session_flags)],
  };
}

