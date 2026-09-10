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
  patient_report: "Relato relevante",
  symptom: "Síntoma",
  allergy: "Alergia",
  medication_history: "Medicamento habitual",
  vital_sign: "Signo vital",
  exam_finding: "Hallazgo clínico",
  clinical_assessment: "Evaluación clínica",
  diagnosis: "Diagnóstico documentado",
  medication_order: "Orden farmacológica",
  medication_administration: "Medicamento administrado",
  procedure_order: "Procedimiento solicitado",
  procedure_performed: "Procedimiento realizado",
  lab_order: "Laboratorio solicitado",
  imaging_order: "Estudio de imagen solicitado",
  consult_order: "Equipo o especialista solicitado",
  result: "Resultado",
  code_event: "Respuesta crítica activada",
  transfer: "Traslado",
  disposition: "Disposición",
  handoff: "Transferencia clínica",
};

const fieldLabels: Record<string, string> = {
  name: "Nombre",
  request: "Solicitud",
  fact: "Relato",
  symptom: "Síntoma",
  finding: "Hallazgo",
  diagnosis: "Diagnóstico",
  medication: "Medicamento",
  dose: "Dosis",
  route: "Vía",
  frequency: "Frecuencia",
  value: "Valor",
  unit: "Unidad",
  body_site: "Región",
  destination: "Destino",
  result: "Resultado",
  status: "Estado",
  explicit_command: "Comando confirmado",
};

const stateLabels: Record<string, string> = {
  reported: "Reportado",
  observed: "Observado",
  considered: "Considerado",
  planned: "Planificado",
  pending_confirmation: "Pendiente de confirmación",
  awaiting_confirmation: "Requiere confirmación",
  confirmed: "Confirmada",
  dispatched: "Enviada",
  accepted: "Recibida",
  in_progress: "En ejecución",
  administered: "Administrado",
  completed: "Completada",
  cancelled: "Cancelada",
  denied: "Descartado",
  failed: "Sin conexión",
  unknown: "Por verificar",
};

const speakerLabels: Record<string, string> = {
  patient: "Paciente",
  physician: "Profesional",
  nurse: "Enfermería",
  paramedic: "Paramédico",
  family: "Familiar",
  system: "PULSO",
  unknown: "Interlocutor",
};

const languageLabels: Record<string, string> = {
  de: "Alemán",
  cs: "Checo",
  en: "Inglés",
  es: "Español",
  fi: "Finés",
  fr: "Francés",
  it: "Italiano",
  nl: "Neerlandés",
  pt: "Portugués",
  sv: "Sueco",
};

const demoScenarios = [
  {
    label: "Trauma multilingüe",
    description: "Barrera de idioma, trauma y coordinación con imagenología.",
    patient: "I fell from a ladder. My chest hurts and I cannot breathe well.",
    physician:
      "Paciente con dolor torácico y dificultad respiratoria tras caída. Pulso, activar equipo de trauma y solicitar radiografía portátil de tórax.",
  },
  {
    label: "Código ictus",
    description: "Déficit neurológico súbito y activación del equipo especializado.",
    patient: "Mi brazo derecho se quedó sin fuerza y me cuesta hablar.",
    physician:
      "Déficit neurológico focal de inicio súbito. Pulso, activar equipo Código Ictus y solicitar tomografía simple de cráneo.",
  },
  {
    label: "Alerta de sepsis",
    description: "Síntomas sistémicos, evaluación y solicitud urgente de laboratorio.",
    patient: "Tengo fiebre, escalofríos y me siento confundido desde anoche.",
    physician:
      "Hipotensión y alteración del estado mental con sospecha de infección. Pulso, activar equipo de sepsis y solicitar laboratorio urgente.",
  },
  {
    label: "Crisis de salud mental",
    description: "Evaluación segura y solicitud de apoyo especializado.",
    patient: "Estoy muy angustiado y siento que puedo hacerme daño.",
    physician:
      "Paciente con riesgo de autolesión, mantener acompañamiento continuo. Pulso, solicitar Psicología y Psiquiatría de Urgencias.",
  },
  {
    label: "Código azul",
    description: "Paro cardiorrespiratorio y activación inmediata del equipo de respuesta.",
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
    if (demo) await request({ action: "reset_demo" }, "Preparando demostración");
    const result = await request<Snapshot>(
      { action: "start", bed, clinician_id: clinician },
      "Iniciando atención",
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
      "Analizando hechos clínicos",
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
        "Analizando audio clínico",
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
      "Preparando audio",
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
      `Enviando a ${signatureOrder.destination}`,
    );
    setSnapshot(result);
    const orderId = signatureOrder.id;
    setSignatureOrder(null);
    if (demo) {
      for (const delay of [450, 650, 850]) {
        await new Promise((resolveDelay) => window.setTimeout(resolveDelay, delay));
        result = await request<Snapshot>(
          { action: "simulate_step", encounter_id: encounter.id, order_id: orderId },
          "Actualizando respuesta simulada",
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
      "Generando informe clínico",
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
            <p>Captura hechos relevantes y coordina la atención clínica en tiempo real.</p>
          </motion.section>
          <motion.section initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="start-card">
            <div className="card-heading">
              <div><span className="section-kicker">Nueva atención</span><h2>Preparar cubículo</h2></div>
              <Stethoscope size={24} />
            </div>
            <div className="field-grid">
              <label>Cubículo<input value={bed} onChange={(event) => setBed(event.target.value)} /></label>
              <label>Profesional<input value={clinician} onChange={(event) => setClinician(event.target.value)} /></label>
            </div>
            <div className="demo-switch">
              <div><strong>Demostración</strong><small>Casos sintéticos y respuestas hospitalarias simuladas</small></div>
              <button className={demo ? "switch active" : "switch"} onClick={() => setDemo(!demo)} aria-label="Cambiar modo"><span /></button>
            </div>
            <button className="primary wide" onClick={startEncounter} disabled={Boolean(busy) || !bed.trim() || !clinician.trim()}>
              Iniciar atención <ArrowUpRight size={18} />
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
        <nav><div className="nav-item active"><Activity size={19} /><span>Atención</span></div></nav>
        <div className="sidebar-bottom">
          <div className="profile"><span>{clinician.slice(0, 2).toUpperCase()}</span><div><strong>{clinician}</strong><small>Profesional activo</small></div></div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="patient-title">
            <div className="patient-avatar"><UserRound size={20} /></div>
            <div><span>{encounter.patient_ref}</span><small>{encounter.bed} · Urgencias</small></div>
            <button className="identity-button" onClick={() => setIdentityOpen(true)}><IdCard size={15} /> Identificar</button>
            {(!demo || isCritical) && (
              <span className={`encounter-state ${isCritical ? "red" : ""}`}>
                <span className="status-dot" />
                {isCritical ? "RESPUESTA CRÍTICA" : recording ? "ESCUCHA ACTIVA" : "MICRÓFONO SILENCIADO"}
              </span>
            )}
          </div>
          <div className="top-actions">
            {demo && <span className="demo-label">DEMOSTRACIÓN</span>}
            <button className="ghost" onClick={closeEncounter} disabled={encounter.state === "closed"}><BadgeCheck size={17} /> Finalizar</button>
          </div>
        </header>

        <div className="clinical-grid">
          <section className="timeline-panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Atención en curso</span>
                <h2>{activeView === "conversation" ? "Conversación en vivo" : "Historia clínica relevante"}</h2>
              </div>
              <div className="panel-tools">
                {backgroundActivity && <span className="background-status"><span />{backgroundActivity}</span>}
                <div className="view-tabs">
                  <button className={activeView === "conversation" ? "active" : ""} onClick={() => setActiveView("conversation")}>
                    <MessageSquareText size={13} /> Conversación <span>{snapshot.utterances.length}</span>
                  </button>
                  <button className={activeView === "clinical" ? "active" : ""} onClick={() => setActiveView("clinical")}>
                    <Activity size={13} /> Registro clínico <span>{snapshot.events.length}</span>
                  </button>
                </div>
              </div>
            </div>
            {activeView === "conversation" ? (
              <div className="conversation" ref={conversationRef}>
                {snapshot.utterances.length === 0 ? (
                  <div className="empty-state"><MessageSquareText size={28} /><h3>Escuchando la conversación</h3><p>Las intervenciones aparecerán aquí; el informe conservará únicamente la información clínica relevante.</p></div>
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
                          <button onClick={() => playTranslation(utterance, encounter.language)}><Volume2 size={14} /> Escuchar</button>
                        </div>
                      )}
                    </motion.article>
                  );
                })}
              </div>
            ) : (
              <div className="timeline">
                {latestEvents.length === 0 ? (
                  <div className="empty-state"><Activity size={28} /><h3>Sin eventos clínicos</h3><p>Las preguntas y la conversación general permanecen visibles en Conversación, pero no se incorporan al registro clínico.</p></div>
                ) : latestEvents.map((event, index) => (
                  <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} key={event.id} className="timeline-event">
                    <div className={`event-node ${event.actionable ? "action" : ""}`}>{event.actionable ? <Radio size={14} /> : <Check size={14} />}</div>
                    <div className="event-body">
                      <div><strong>{eventLabels[event.type] || cleanText(event.type)}</strong><time>{shortTime(event.created_at)}</time></div>
                      <p>{payloadText(event.payload)}</p>
                      <div className="event-meta"><span>{stateLabels[event.state] || cleanText(event.state)}</span>{event.confidence != null && <span>{Math.round(event.confidence * 100)}% confianza</span>}</div>
                    </div>
                    {index < latestEvents.length - 1 && <span className="event-line" />}
                  </motion.article>
                ))}
              </div>
            )}
            {demo ? (
              <section className="demo-console">
                <div className="demo-console-heading"><div><strong>Casos de demostración</strong><span>Selecciona un caso para ejecutar ambas intervenciones.</span></div><button className={recording ? "record-button active" : "record-button"} onClick={toggleDemoRecording}>{recording ? <CircleStop size={17} /> : <Mic size={17} />}{recording ? "Detener demo en vivo" : "Demo en vivo"}</button></div>
                <div className="scenario-grid">
                  {demoScenarios.map((scenario, index) => (
                    <button key={scenario.label} className={activeScenario === index ? "selected" : ""} onClick={() => runScenario(index)} disabled={Boolean(runningScenario)}>
                      <strong>{scenario.label}</strong><span>{scenario.description}</span>{runningScenario === scenario.label && <small>Ejecutando…</small>}
                    </button>
                  ))}
                </div>
                {activeScenario !== null && <div className="demo-script"><div><small>Paciente</small><p>{demoScenarios[activeScenario].patient}</p></div><div><small>Profesional</small><p>{demoScenarios[activeScenario].physician}</p></div></div>}
              </section>
            ) : (
              <section className="live-bar"><span className="live-wave"><i /><i /><i /><i /></span><div><strong>{recording ? "Micrófono activo" : "Micrófono silenciado"}</strong><small>{recording ? "La captura continúa durante toda la atención y conserva únicamente los eventos relevantes." : "La escucha está pausada hasta que vuelvas a activarla."}</small></div><button className={recording ? "record-button active" : "record-button"} onClick={toggleOfficialListening}>{recording ? <MicOff size={17} /> : <Mic size={17} />}{recording ? "Silenciar" : "Reactivar"}</button></section>
            )}
          </section>

          <aside className="orders-panel">
            <div className="panel-header"><div><span className="section-kicker">Lazo cerrado</span><h2>Coordinación</h2></div><span className="count-badge">{snapshot.orders.length}</span></div>
            <div className="orders-list">
              {snapshot.orders.length === 0 ? (
                <div className="orders-empty"><Radio size={24} /><p>Las órdenes explícitas aparecerán aquí para revisión y firma.</p><small>Di “Pulso” antes de una orden o activación.</small></div>
              ) : snapshot.orders.map((order) => {
                const isDone = order.state === "completed";
                const isCancelled = order.state === "cancelled";
                const simulated = snapshot.transitions.some((item) => item.order_id === order.id && item.actor.startsWith("demo."));
                return (
                  <motion.article layout key={order.id} className={`order-card ${isDone ? "done" : ""}`}>
                    <div className="order-top"><span className="destination"><Radio size={14} />{order.destination}</span>{simulated && <span className="simulated">SIMULADO</span>}</div>
                    <h3>{cleanText(order.request)}</h3>
                    <div className="order-state"><span className={`order-state-icon ${order.state}`}>{isDone ? <Check size={13} /> : isCancelled ? <X size={13} /> : <Activity size={13} />}</span><strong>{stateLabels[order.state] || cleanText(order.state)}</strong></div>
                    {order.state === "awaiting_confirmation" && <div className="order-actions"><button className="confirm" onClick={() => setSignatureOrder(order)}>Revisar y firmar</button><button className="cancel" onClick={() => cancelOrder(order)}><XCircle size={16} /></button></div>}
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
        {signatureOrder && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><button className="modal-close" onClick={() => setSignatureOrder(null)}><X size={18} /></button><span className="modal-icon"><ShieldCheck size={22} /></span><span className="section-kicker">Confirmación clínica</span><h2>Revisar antes de enviar</h2><div className="readback"><small>Destino</small><strong>{signatureOrder.destination}</strong><p>{cleanText(signatureOrder.request)}</p></div><label>Firma del profesional<input value={signature} onChange={(event) => setSignature(event.target.value)} /></label><p className="safety-copy">La orden se envía únicamente después de validar contenido, destino e identidad profesional.</p><button className="primary wide" onClick={confirmOrder}>Confirmar y enviar</button></motion.div></motion.div>}
      </AnimatePresence>

      <AnimatePresence>
        {identityOpen && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal compact" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><button className="modal-close" onClick={() => setIdentityOpen(false)}><X size={18} /></button><span className="modal-icon"><IdCard size={22} /></span><span className="section-kicker">Identificación</span><h2>Actualizar paciente</h2><label>Nombre o referencia<input value={patientRef} onChange={(event) => setPatientRef(event.target.value)} autoFocus /></label><button className="primary wide" onClick={identifyPatient}>Guardar identificación</button></motion.div></motion.div>}
      </AnimatePresence>

      <AnimatePresence>
        {exports && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><motion.div className="modal export-modal" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }}><span className="modal-icon"><FileText size={22} /></span><span className="section-kicker">Atención finalizada</span><h2>Informe clínico generado</h2><p>El informe estructurado de Word y el paquete FHIR quedaron guardados en el equipo.</p><div className="export-actions"><button className="primary" onClick={() => window.pulso.showExport(exports.reportPath)}>Ver Word</button><button className="secondary" onClick={() => window.pulso.showExport(exports.fhirPath)}>Ver FHIR</button><button className="secondary" onClick={newEncounter}>Nueva atención</button></div></motion.div></motion.div>}
      </AnimatePresence>

      {message && <button className="toast" onClick={() => setMessage("")}><span>{message}</span><X size={15} /></button>}
    </div>
  );
}

export default App;
