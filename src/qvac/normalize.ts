import type { ExtractionResult } from "./types.js";

const orderTypes = new Set([
  "medication_order",
  "procedure_order",
  "lab_order",
  "imaging_order",
  "consult_order",
  "code_event",
  "transfer",
]);

function sanitizeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value
      .replace(/\s*\[(?:incomplete|truncated|inaudible|unclear)\]\s*/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
  }
  if (Array.isArray(value)) return value.map(sanitizeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .map(([key, item]) => [key, sanitizeValue(item)])
        .filter(([, item]) => item !== "" && item !== null),
    );
  }
  return value;
}

export function normalizeExtraction(
  result: ExtractionResult,
  input: { patient_ref: string; utterances: Array<{ id: string; text?: string }> },
): ExtractionResult {
  const utteranceIds = new Set(input.utterances.map((item) => item.id));
  const utteranceText = new Map(input.utterances.map((item) => [item.id, item.text]));
  const eventIds = new Set(result.events.map((item) => item.event_id));
  const events = result.events
    .filter((event) => event.evidence_utterance_ids.every((id) => utteranceIds.has(id)))
    .map((event) => {
      const isOrder = orderTypes.has(event.type);
      const supersedes = event.supersedes_event_id;
      const evidence = event.evidence_utterance_ids
        .map((id) => utteranceText.get(id))
        .filter((text): text is string => Boolean(text))
        .join(" ");
      return {
        ...event,
        payload:
          event.type === "patient_report" && evidence
            ? { fact: sanitizeValue(evidence) }
            : (sanitizeValue(event.payload) as Record<string, unknown>),
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
