import { describe, expect, it } from "vitest";

import { parseDiarization, tagTranslationInput } from "../src/qvac/engine.js";
import { normalizeExtraction } from "../src/qvac/normalize.js";

describe("PULSO extraction normalization", () => {
  it("binds events to the active patient and rejects unknown evidence", () => {
    const result = normalizeExtraction(
      {
        events: [
          {
            event_id: "e1",
            type: "symptom",
            state: "reported",
            actor_role: "patient",
            patient_ref: "wrong-patient",
            evidence_utterance_ids: ["u1"],
            payload: { name: "dolor" },
            actionable: true,
            confirmation_required: true,
            missing_fields: [],
            rag_required: false,
          },
          {
            event_id: "e2",
            type: "diagnosis",
            state: "reported",
            actor_role: "unknown",
            patient_ref: null,
            evidence_utterance_ids: ["invented"],
            payload: {},
            actionable: false,
            confirmation_required: false,
            missing_fields: [],
            rag_required: false,
          },
        ],
        ignored_utterance_ids: ["u1", "invented"],
        session_flags: ["audio_uncertain", "audio_uncertain"],
      },
      { patient_ref: "active-patient", utterances: [{ id: "u1" }] },
    );
    expect(result.events).toHaveLength(1);
    expect(result.events[0].patient_ref).toBe("active-patient");
    expect(result.events[0].actionable).toBe(false);
    expect(result.ignored_utterance_ids).toEqual(["u1"]);
    expect(result.session_flags).toEqual(["audio_uncertain"]);
  });
});

describe("TranslatePsy target selection", () => {
  it("adds the documented target tag only for English source text", () => {
    expect(tagTranslationInput("Chest pain", "en", "es")).toBe(
      "##ES Chest pain",
    );
    expect(tagTranslationInput("Dolor torácico", "es", "en")).toBe(
      "Dolor torácico",
    );
  });
});

describe("Sortformer diarization", () => {
  it("normalizes seconds and clock timestamps to milliseconds", () => {
    expect(
      parseDiarization(
        "Speaker 2: 3.25s - 7.5s\nSpeaker 1: 00:00:08.0 - 00:00:10.5",
      ),
    ).toEqual([
      { speaker: 2, startMs: 3250, endMs: 7500 },
      { speaker: 1, startMs: 8000, endMs: 10500 },
    ]);
  });
});
