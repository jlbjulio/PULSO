import {
  Activity,
  ArrowUpRight,
  BadgeCheck,
  Check,
  CircleStop,
  FileText,
  HeartPulse,
  IdCard,
  Languages,
  MessageSquareText,
  Mic,
  MicOff,
  Radio,
  ShieldCheck,
  Stethoscope,
  UserRound,
  Volume2,
  X,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

type Json = Record<string, unknown>;

type Encounter = {
  id: string;
  patient_ref: string;
  bed: string;
  clinician_id: string;
  state: string;
  critical_mode: boolean;
  language: string;
};

type ClinicalEvent = {
  id: string;
  type: string;
  state: string;
  payload: Json;
  actionable: boolean;
  confidence?: number;
  created_at: string;
};

type Order = {
  id: string;
  destination: string;
  request: string;
  state: string;
};

type Utterance = {
  id: string;
  speaker: string;
  language: string;
  original_text: string;
  translated_text?: string;
  created_at: string;
};

type Transition = {
  order_id: string;
  actor: string;
};

type Snapshot = {
  encounter: Encounter;
  events: ClinicalEvent[];
  orders: Order[];
  utterances: Utterance[];
  transitions: Transition[];
};

type AudioSession = {
  context: AudioContext;
  stream: MediaStream;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  chunks: Float32Array[];
  timer?: number;
  processing: boolean;
  encounterId: string;
  startedAt: number;
  lastVoiceAt: number;
};

type ExportResult = {
  reportPath: string;
  fhirPath: string;
};

const eventLabels: Record<string, string> = {
  patient_report: "Relevant history",
  symptom: "Symptom",
  allergy: "Allergy",
  medication_history: "Current medication",
  vital_sign: "Vital sign",
  exam_finding: "Clinical finding",
  clinical_assessment: "Clinical assessment",
  diagnosis: "Documented diagnosis",
  medication_order: "Medication order",
  medication_administration: "Medication administered",
  procedure_order: "Procedure ordered",
  procedure_performed: "Procedure performed",
  lab_order: "Laboratory order",
  imaging_order: "Imaging order",
  consult_order: "Team or specialist request",
  result: "Result",
  code_event: "Critical response activated",
  transfer: "Transfer",
  disposition: "Disposition",
  handoff: "Clinical handoff",
};

const fieldLabels: Record<string, string> = {
  name: "Name", request: "Request", fact: "History", symptom: "Symptom",
  finding: "Finding", diagnosis: "Diagnosis", medication: "Medication",
  dose: "Dose", route: "Route", frequency: "Frequency", value: "Value",
  unit: "Unit", body_site: "Region", destination: "Destination",
  result: "Result", status: "Status", explicit_command: "Confirmed command",
};

const stateLabels: Record<string, string> = {
  reported: "Reported", observed: "Observed", considered: "Considered",
  planned: "Planned", pending_confirmation: "Pending confirmation",
  awaiting_confirmation: "Awaiting confirmation", confirmed: "Confirmed",
  dispatched: "Dispatched", accepted: "Accepted", in_progress: "In progress",
  administered: "Administered", completed: "Completed", cancelled: "Cancelled",
  denied: "Denied", failed: "Disconnected", unknown: "Unverified",
};

const speakerLabels: Record<string, string> = {
  patient: "Patient", physician: "Clinician", nurse: "Nurse",
  paramedic: "Paramedic", family: "Family member",
  system: "PULSO",
  unknown: "Speaker",
};

const languageLabels: Record<string, string> = {
  de: "German", cs: "Czech", en: "English", es: "Spanish", fi: "Finnish",
  fr: "French", it: "Italian", nl: "Dutch", pt: "Portuguese", sv: "Swedish",
};

const demoScenarios = [
  {
    label: "Multilingual trauma",
    description: "Language barrier, trauma response, and imaging coordination.",
    patient: "I fell from a ladder. My chest hurts and I cannot breathe well.",
    physician:
      "Paciente con dolor torácico y dificultad respiratoria tras caída. Pulso, activar equipo de trauma y solicitar radiografía portátil de tórax.",
  },
  {
    label: "Stroke code",
    description: "Sudden neurological deficit and specialist team activation.",
    patient: "Mi brazo derecho se quedó sin fuerza y me cuesta hablar.",
    physician:
      "Déficit neurológico focal de inicio súbito. Pulso, activar equipo Código Ictus y solicitar tomografía simple de cráneo.",
  },
  {
    label: "Sepsis alert",
    description: "Systemic symptoms, assessment, and urgent laboratory request.",
    patient: "Tengo fiebre, escalofríos y me siento confundido desde anoche.",
    physician:
      "Hipotensión y alteración del estado mental con sospecha de infección. Pulso, activar equipo de sepsis y solicitar laboratorio urgente.",
  },
  {
    label: "Mental health crisis",
    description: "Safety assessment and specialist support request.",
    patient: "Estoy muy angustiado y siento que puedo hacerme daño.",
    physician:
      "Paciente con riesgo de autolesión, mantener acompañamiento continuo. Pulso, solicitar Psicología y Psiquiatría de Urgencias.",
  },
  {
    label: "Code Blue",
    description: "Cardiorespiratory arrest and immediate response-team activation.",
    patient: "El paciente no responde y no presenta respiración normal.",
    physician:
      "Paciente inconsciente, sin pulso y sin respiración. Pulso, activar Código Azul e iniciar reanimación cardiopulmonar.",
  },
];

function cleanText(value: unknown): string {
  if (Array.isArray(value)) return value.map(cleanText).join(", ");
  if (value && typeof value === "object") return Object.values(value).map(cleanText).join(" · ");
  return String(value ?? "")
    .replace(/\s*\[(?:incomplete|truncated|inaudible|unclear)\]\s*/gi, " ")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function payloadText(payload: Json): string {
  const entries = Object.entries(payload).filter(
    ([key, value]) => key !== "explicit_command" && value !== null && value !== "",
  );
  if (entries.length === 1 && ["content", "text", "value"].includes(entries[0][0])) {
    return cleanText(entries[0][1]);
  }
  return entries
    .map(([key, value]) =>
      ["content", "text", "value"].includes(key)
        ? cleanText(value)
        : `${fieldLabels[key] || cleanText(key)}: ${cleanText(value)}`,
    )
    .join(" · ");
}

function shortTime(value: string): string {
  return new Intl.DateTimeFormat("es-PA", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function encodeWav(chunks: Float32Array[], sampleRate: number): Uint8Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const chunk of chunks) {
    for (const sample of chunk) {
      const limited = Math.max(-1, Math.min(1, sample));
      view.setInt16(offset, limited < 0 ? limited * 0x8000 : limited * 0x7fff, true);
      offset += 2;
    }
  }
  return new Uint8Array(buffer);
}

function containsSpeech(chunks: Float32Array[]): boolean {
  let energy = 0;
  let samples = 0;
  for (const chunk of chunks) {
    for (const sample of chunk) energy += sample * sample;
    samples += chunk.length;
  }
  return samples > 0 && Math.sqrt(energy / samples) > 0.008;
}

function Logo() {
  return (
    <div className="logo">
      <span className="logo-mark"><HeartPulse size={21} strokeWidth={2.4} /></span>
      <span>PULSO</span>
    </div>
  );
}

function App() {
  const [demo, setDemo] = useState(true);
  const [bed, setBed] = useState("Trauma 2");
  const [clinician, setClinician] = useState("dra.rivera");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState("");
  const [backgroundActivity, setBackgroundActivity] = useState("");
  const [message, setMessage] = useState("");
  const [recording, setRecording] = useState(false);
  const [runningScenario, setRunningScenario] = useState("");
  const [activeScenario, setActiveScenario] = useState<number | null>(null);
  const [signatureOrder, setSignatureOrder] = useState<Order | null>(null);
  const [signature, setSignature] = useState("dra.rivera / firma local");
  const [identityOpen, setIdentityOpen] = useState(false);
  const [patientRef, setPatientRef] = useState("");
  const [exports, setExports] = useState<ExportResult | null>(null);
  const [activeView, setActiveView] = useState<"conversation" | "clinical">("conversation");
  const audioSession = useRef<AudioSession | null>(null);
  const conversationRef = useRef<HTMLDivElement | null>(null);

  const encounter = snapshot?.encounter;
  const isCritical = encounter?.state === "critical";
  const latestEvents = useMemo(() => [...(snapshot?.events || [])].reverse(), [snapshot?.events]);
  const utteranceCount = snapshot?.utterances.length ?? 0;

  useEffect(() => setSignature(`${clinician} / firma local`), [clinician]);
  useEffect(() => () => { void stopMicrophone(false); }, []);
  useEffect(() => {
    if (activeView !== "conversation") return;
    window.requestAnimationFrame(() => {
      const element = conversationRef.current;
      if (element) element.scrollTop = element.scrollHeight;
    });
  }, [activeView, utteranceCount]);

  async function request<T>(payload: Json, label = "Procesando", blocking = true): Promise<T> {
    if (blocking) setBusy(label);
    else setBackgroundActivity(label);
    setMessage("");
    try {
      return await window.pulso.request<T>({ ...payload, demo });
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      if (!text.includes("no speech was detected")) setMessage(text);
      throw error;
    } finally {
      if (blocking) setBusy("");
      else setBackgroundActivity("");
    }
  }

  async function startEncounter() {
    if (demo) await request({ action: "reset_demo" }, "Preparing demo");
    const result = await request<Snapshot>(
      { action: "start", bed, clinician_id: clinician },
      "Starting encounter",
    );
    setSnapshot(result);
    setPatientRef(result.encounter.patient_ref);
    if (!demo) {
      try {
        await startMicrophone(true, result.encounter.id);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    }
  }

  async function captureText(text: string, speaker: "patient" | "physician") {
    if (!encounter) return;
    const result = await request<Snapshot>(
      {
        action: "capture_text",
        encounter_id: encounter.id,
        text,
        speaker,
        language: speaker === "physician" ? "es" : "auto",
        actor: clinician,
      },
      "Extracting clinical facts",
    );
    setSnapshot(result);
  }

  async function runScenario(index: number) {
    const scenario = demoScenarios[index];
    if (!encounter || runningScenario) return;
    setActiveScenario(index);
    setRunningScenario(scenario.label);
    try {
      await captureText(scenario.patient, "patient");
      await captureText(scenario.physician, "physician");
    } finally {
      setRunningScenario("");
    }
  }

  async function flushAudio(session: AudioSession, blocking = false) {
    if (session.processing || session.chunks.length === 0) return;
    const chunks = session.chunks.splice(0);
    session.startedAt = Date.now();
    session.lastVoiceAt = 0;
    const duration = chunks.reduce((total, chunk) => total + chunk.length, 0) / session.context.sampleRate;
    if (duration < 1 || !containsSpeech(chunks)) return;
    session.processing = true;
    try {
      const bytes = encodeWav(chunks, session.context.sampleRate);
      const path = await window.pulso.saveRecording(bytes);
      const result = await request<Snapshot>(
        {
          action: "capture_audio",
          encounter_id: session.encounterId,
          audio_path: path,
          actor: clinician,
        },
        "Processing clinical audio",
        blocking,
      );
      setSnapshot(result);
    } catch (error) {
      if (blocking) throw error;
    } finally {
      session.processing = false;
    }
  }

  async function startMicrophone(continuous: boolean, encounterId: string) {
    if (audioSession.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const context = new AudioContext();
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const session: AudioSession = {
      context,
      stream,
      source,
      processor,
      chunks: [],
      processing: false,
      encounterId,
      startedAt: Date.now(),
      lastVoiceAt: 0,
    };
    processor.onaudioprocess = (event) => {
      const chunk = new Float32Array(event.inputBuffer.getChannelData(0));
      session.chunks.push(chunk);
      let energy = 0;
      for (const sample of chunk) energy += sample * sample;
      if (Math.sqrt(energy / chunk.length) > 0.01) session.lastVoiceAt = Date.now();
    };
    source.connect(processor);
    processor.connect(context.destination);
    if (continuous) {
      session.timer = window.setInterval(() => {
        const now = Date.now();
        const duration = now - session.startedAt;
        const endedPhrase = session.lastVoiceAt > 0 && now - session.lastVoiceAt > 1600;
        if ((endedPhrase && duration > 1500) || duration > 12000) void flushAudio(session);
      }, 400);
    }
    audioSession.current = session;
    setRecording(true);
  }

  async function stopMicrophone(processFinalChunk: boolean) {
    const session = audioSession.current;
    if (!session) return;
    if (session.timer) window.clearInterval(session.timer);
    try {
      if (processFinalChunk) await flushAudio(session, true);
    } finally {
      session.processor.disconnect();
      session.source.disconnect();
      session.stream.getTracks().forEach((track) => track.stop());
      if (session.context.state !== "closed") await session.context.close();
      audioSession.current = null;
      setRecording(false);
    }
  }

  async function toggleDemoRecording() {
    try {
      if (recording) await stopMicrophone(true);
      else if (encounter) await startMicrophone(false, encounter.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function toggleOfficialListening() {
    if (demo || !encounter) return;
    try {
      if (recording) await stopMicrophone(false);
      else await startMicrophone(true, encounter.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function translationTarget(utterance: Utterance, patientLanguage: string) {
    return utterance.language === "es" ? patientLanguage : "es";
  }

  async function playTranslation(
    utterance: Utterance,
    patientLanguage = encounter?.language || "es",
    blocking = true,
  ) {
    if (!utterance.translated_text) return;
    const targetLanguage = translationTarget(utterance, patientLanguage);
    const result = await request<{ output: string }>(
      {
        action: "speak",
        text: utterance.translated_text,
        language: targetLanguage,
      },
      "Preparing audio",
      blocking,
    );
    const bytes = Uint8Array.from(await window.pulso.readRuntimeAudio(result.output));
    const url = URL.createObjectURL(new Blob([bytes.buffer], { type: "audio/wav" }));
    const audio = new Audio(url);
    audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
    await audio.play();
  }

  async function identifyPatient() {
    if (!encounter || !patientRef.trim()) return;
    const result = await request<Snapshot>({
      action: "identify_patient",
      encounter_id: encounter.id,
      patient_ref: patientRef,
      actor: clinician,
    });
    setSnapshot(result);
    setIdentityOpen(false);
  }

  async function confirmOrder() {
    if (!encounter || !signatureOrder) return;
    let result = await request<Snapshot>(
      {
        action: "order_confirm_dispatch",
        encounter_id: encounter.id,
        order_id: signatureOrder.id,
        actor: clinician,
        signature,
      },
      `Dispatching to ${signatureOrder.destination}`,
    );
    setSnapshot(result);
    const orderId = signatureOrder.id;
    setSignatureOrder(null);
    if (demo) {
      for (const delay of [450, 650, 850]) {
        await new Promise((resolveDelay) => window.setTimeout(resolveDelay, delay));
        result = await request<Snapshot>(
          { action: "simulate_step", encounter_id: encounter.id, order_id: orderId },
          "Updating simulated response",
        );
        setSnapshot(result);
      }
    }
  }

  async function cancelOrder(order: Order) {
    if (!encounter) return;
    const result = await request<Snapshot>({
      action: "order_cancel",
      encounter_id: encounter.id,
      order_id: order.id,
      actor: clinician,
    });
    setSnapshot(result);
  }

  async function closeEncounter() {
    if (!encounter) return;
    await stopMicrophone(false);
    const result = await request<{
      snapshot: Snapshot;
      report_path: string;
      fhir_path: string;
    }>(
      { action: "close", encounter_id: encounter.id, actor: clinician, signature },
      "Generating clinical report",
    );
    setSnapshot(result.snapshot);
    setExports({ reportPath: result.report_path, fhirPath: result.fhir_path });
  }

  function newEncounter() {
    void stopMicrophone(false);
    setSnapshot(null);
    setExports(null);
    setMessage("");
    setPatientRef("");
    setSignatureOrder(null);
    setActiveView("conversation");
  }

  if (!snapshot) {
    return (
      <div className="onboarding-shell">
        <header className="onboarding-nav"><Logo /></header>
        <main className="onboarding">
          <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="hero-copy">
            <h1>PULSO</h1>
            <p>Capture relevant facts and coordinate emergency care in real time.</p>
          </motion.section>
          <motion.section initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="start-card">
            <div className="card-heading">
              <div><span className="section-kicker">New encounter</span><h2>Prepare treatment bay</h2></div>
              <Stethoscope size={24} />
            </div>
            <div className="field-grid">
              <label>Treatment bay<input value={bed} onChange={(event) => setBed(event.target.value)} /></label>
              <label>Clinician<input value={clinician} onChange={(event) => setClinician(event.target.value)} /></label>
            </div>
            <div className="demo-switch">
              <div><strong>Demo mode</strong><small>Synthetic cases and simulated hospital responses</small></div>
              <button className={demo ? "switch active" : "switch"} onClick={() => setDemo(!demo)} aria-label="Toggle mode"><span /></button>
            </div>
            <button className="primary wide" onClick={startEncounter} disabled={Boolean(busy) || !bed.trim() || !clinician.trim()}>
              Start encounter <ArrowUpRight size={18} />
            </button>
            {message && <p className="error-text">{message}</p>}
          </motion.section>
        </main>
      </div>
    );
  }

  if (!encounter) return null;

  return (
    <div className={isCritical ? "app-shell critical" : "app-shell"}>
      <aside className="sidebar">
        <Logo />
        <nav><div className="nav-item active"><Activity size={19} /><span>Encounter</span></div></nav>
        <div className="sidebar-bottom">
          <div className="profile"><span>{clinician.slice(0, 2).toUpperCase()}</span><div><strong>{clinician}</strong><small>Active clinician</small></div></div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="patient-title">
            <div className="patient-avatar"><UserRound size={20} /></div>
            <div><span>{encounter.patient_ref}</span><small>{encounter.bed} · Emergency</small></div>
            <button className="identity-button" onClick={() => setIdentityOpen(true)}><IdCard size={15} /> Identify</button>
            {(!demo || isCritical) && (
              <span className={`encounter-state ${isCritical ? "red" : ""}`}>
                <span className="status-dot" />
                {isCritical ? "CRITICAL RESPONSE" : recording ? "ACTIVE LISTENING" : "MICROPHONE MUTED"}
              </span>
            )}
          </div>
          <div className="top-actions">
            {demo && <span className="demo-label">DEMO</span>}
            <button className="ghost" onClick={closeEncounter} disabled={encounter.state === "closed"}><BadgeCheck size={17} /> Finish</button>
          </div>
        </header>

        <div className="clinical-grid">
          <section className="timeline-panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Active encounter</span>
                <h2>{activeView === "conversation" ? "Live conversation" : "Relevant clinical record"}</h2>
              </div>
              <div className="panel-tools">
                {backgroundActivity && <span className="background-status"><span />{backgroundActivity}</span>}
                <div className="view-tabs">
                  <button className={activeView === "conversation" ? "active" : ""} onClick={() => setActiveView("conversation")}>
                    <MessageSquareText size={13} /> Conversation <span>{snapshot.utterances.length}</span>
                  </button>
                  <button className={activeView === "clinical" ? "active" : ""} onClick={() => setActiveView("clinical")}>
                    <Activity size={13} /> Clinical record <span>{snapshot.events.length}</span>
                  </button>
                </div>
              </div>
            </div>
            {activeView === "conversation" ? (
              <div className="conversation" ref={conversationRef}>
                {snapshot.utterances.length === 0 ? (
                  <div className="empty-state"><MessageSquareText size={28} /><h3>Listening to the conversation</h3><p>Utterances appear here; the report preserves only clinically relevant information.</p></div>
                ) : snapshot.utterances.map((utterance) => {
                  const targetLanguage = translationTarget(utterance, encounter.language);
                  return (
                    <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} key={utterance.id} className={`utterance ${utterance.speaker}`}>
                      <div className="utterance-heading">
                        <div>
                          <strong>{speakerLabels[utterance.speaker] || speakerLabels.unknown}</strong>
                          <span>{languageLabels[utterance.language] || utterance.language.toUpperCase()}</span>
                        </div>
                        <time>{shortTime(utterance.created_at)}</time>
                      </div>
                      <p>{utterance.original_text}</p>
                      {utterance.translated_text && (
                        <div className="utterance-translation">
                          <div><Languages size={13} /><span>{languageLabels[targetLanguage] || targetLanguage.toUpperCase()}</span></div>
                          <p>{utterance.translated_text}</p>
                          <button onClick={() => playTranslation(utterance, encounter.language)}><Volume2 size={14} /> Listen</button>
                        </div>
                      )}
                    </motion.article>
                  );
                })}
              </div>
            ) : (
              <div className="timeline">
                {latestEvents.length === 0 ? (
                  <div className="empty-state"><Activity size={28} /><h3>No clinical events</h3><p>Questions and general conversation remain visible in Conversation but are not added to the clinical record.</p></div>
                ) : latestEvents.map((event, index) => (
                  <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} key={event.id} className="timeline-event">
                    <div className={`event-node ${event.actionable ? "action" : ""}`}>{event.actionable ? <Radio size={14} /> : <Check size={14} />}</div>
                    <div className="event-body">
                      <div><strong>{eventLabels[event.type] || cleanText(event.type)}</strong><time>{shortTime(event.created_at)}</time></div>
                      <p>{payloadText(event.payload)}</p>
                      <div className="event-meta"><span>{stateLabels[event.state] || cleanText(event.state)}</span>{event.confidence != null && <span>{Math.round(event.confidence * 100)}% confidence</span>}</div>
                    </div>
                    {index < latestEvents.length - 1 && <span className="event-line" />}
                  </motion.article>
                ))}
              </div>
            )}
            {demo ? (
              <section className="demo-console">
                <div className="demo-console-heading"><div><strong>Demo cases</strong><span>Select a case to run both sides of the encounter.</span></div><button className={recording ? "record-button active" : "record-button"} onClick={toggleDemoRecording}>{recording ? <CircleStop size={17} /> : <Mic size={17} />}{recording ? "Stop live demo" : "Live demo"}</button></div>
                <div className="scenario-grid">
                  {demoScenarios.map((scenario, index) => (
                    <button key={scenario.label} className={activeScenario === index ? "selected" : ""} onClick={() => runScenario(index)} disabled={Boolean(runningScenario)}>
                      <strong>{scenario.label}</strong><span>{scenario.description}</span>{runningScenario === scenario.label && <small>Running…</small>}
                    </button>
                  ))}
                </div>
                {activeScenario !== null && <div className="demo-script"><div><small>Patient</small><p>{demoScenarios[activeScenario].patient}</p></div><div><small>Clinician</small><p>{demoScenarios[activeScenario].physician}</p></div></div>}
              </section>
            ) : (
              <section className="live-bar"><span className="live-wave"><i /><i /><i /><i /></span><div><strong>{recording ? "Microphone active" : "Microphone muted"}</strong><small>{recording ? "Capture continues throughout the encounter and preserves only relevant events." : "Listening is paused until you resume it."}</small></div><button className={recording ? "record-button active" : "record-button"} onClick={toggleOfficialListening}>{recording ? <MicOff size={17} /> : <Mic size={17} />}{recording ? "Mute" : "Resume"}</button></section>
            )}
          </section>

          <aside className="orders-panel">
            <div className="panel-header"><div><span className="section-kicker">Closed loop</span><h2>Coordination</h2></div><span className="count-badge">{snapshot.orders.length}</span></div>
            <div className="orders-list">
              {snapshot.orders.length === 0 ? (
                <div className="orders-empty"><Radio size={24} /><p>Explicit orders appear here for review and signature.</p><small>Say “Pulso” before an order or activation.</small></div>
              ) : snapshot.orders.map((order) => {
                const isDone = order.state === "completed";
                const isCancelled = order.state === "cancelled";
                const simulated = snapshot.transitions.some((item) => item.order_id === order.id && item.actor.startsWith("demo."));
                return (
                  <motion.article layout key={order.id} className={`order-card ${isDone ? "done" : ""}`}>
                    <div className="order-top"><span className="destination"><Radio size={14} />{order.destination}</span>{simulated && <span className="simulated">SIMULATED</span>}</div>
                    <h3>{cleanText(order.request)}</h3>
                    <div className="order-state"><span className={`order-state-icon ${order.state}`}>{isDone ? <Check size={13} /> : isCancelled ? <X size={13} /> : <Activity size={13} />}</span><strong>{stateLabels[order.state] || cleanText(order.state)}</strong></div>
                    {order.state === "awaiting_confirmation" && <div className="order-actions"><button className="confirm" onClick={() => setSignatureOrder(order)}>Review and sign</button><button className="cancel" onClick={() => cancelOrder(order)}><XCircle size={16} /></button></div>}
                    {!['awaiting_confirmation', 'completed', 'cancelled'].includes(order.state) && <div className="progress-track"><span className={`progress-fill ${order.state}`} /></div>}
                  </motion.article>
                );
              })}
            </div>
          </aside>
        </div>
      </main>

      <AnimatePresence>
        {busy && <motion.div className="busy-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><div className="busy-card"><span className="pulse-ring"><HeartPulse size={24} /></span><strong>{busy}</strong></div></motion.div>}
      </AnimatePresence>

      <AnimatePresence>
        {signatureOrder && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><button className="modal-close" onClick={() => setSignatureOrder(null)}><X size={18} /></button><span className="modal-icon"><ShieldCheck size={22} /></span><span className="section-kicker">Clinical confirmation</span><h2>Review before dispatch</h2><div className="readback"><small>Destination</small><strong>{signatureOrder.destination}</strong><p>{cleanText(signatureOrder.request)}</p></div><label>Clinician signature<input value={signature} onChange={(event) => setSignature(event.target.value)} /></label><p className="safety-copy">The order is dispatched only after its content, destination, and clinician identity are verified.</p><button className="primary wide" onClick={confirmOrder}>Confirm and dispatch</button></motion.div></motion.div>}
      </AnimatePresence>

      <AnimatePresence>
        {identityOpen && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal compact" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><button className="modal-close" onClick={() => setIdentityOpen(false)}><X size={18} /></button><span className="modal-icon"><IdCard size={22} /></span><span className="section-kicker">Identification</span><h2>Update patient</h2><label>Name or reference<input value={patientRef} onChange={(event) => setPatientRef(event.target.value)} autoFocus /></label><button className="primary wide" onClick={identifyPatient}>Save identification</button></motion.div></motion.div>}
      </AnimatePresence>

      <AnimatePresence>
        {exports && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal export-modal" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><span className="modal-icon"><FileText size={22} /></span><span className="section-kicker">Encounter complete</span><h2>Clinical report generated</h2><p>The structured Word report and FHIR bundle were saved locally.</p><div className="export-actions"><button className="primary" onClick={() => window.pulso.showExport(exports.reportPath)}>Open Word report</button><button className="secondary" onClick={() => window.pulso.showExport(exports.fhirPath)}>Open FHIR bundle</button><button className="secondary" onClick={newEncounter}>New encounter</button></div></motion.div></motion.div>}
      </AnimatePresence>

      {message && <button className="toast" onClick={() => setMessage("")}><span>{message}</span><X size={15} /></button>}
    </div>
  );
}

export default App;
