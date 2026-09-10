import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  BookOpenCheck,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleStop,
  FileScan,
  HeartPulse,
  Languages,
  LockKeyhole,
  Mic,
  Radio,
  Search,
  Send,
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
  category: string;
  destination: string;
  request: string;
  state: string;
  updated_at: string;
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
  id: number;
  order_id: string;
  state: string;
  actor: string;
  created_at: string;
};

type Snapshot = {
  encounter: Encounter;
  events: ClinicalEvent[];
  orders: Order[];
  utterances: Utterance[];
  transitions: Transition[];
  dashboard: { active_encounters: number; pending_orders: number; queued_messages: number };
};

type RagResult = {
  content?: string;
  text?: string;
  score?: number;
  metadata?: Json;
};

type AudioSession = {
  context: AudioContext;
  stream: MediaStream;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  chunks: Float32Array[];
};

function encodeWav(chunks: Float32Array[], sampleRate: number): Uint8Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
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

const eventLabels: Record<string, string> = {
  patient_report: "Relato del paciente",
  symptom: "Síntoma",
  allergy: "Alergia",
  medication_history: "Medicamento habitual",
  vital_sign: "Signo vital",
  exam_finding: "Hallazgo",
  clinical_assessment: "Evaluación clínica",
  diagnosis: "Diagnóstico documentado",
  medication_order: "Orden farmacológica",
  medication_administration: "Medicamento administrado",
  procedure_order: "Procedimiento solicitado",
  procedure_performed: "Procedimiento realizado",
  lab_order: "Laboratorio solicitado",
  imaging_order: "Imagen solicitada",
  consult_order: "Equipo solicitado",
  result: "Resultado",
  code_event: "Activación crítica",
  transfer: "Traslado",
  disposition: "Disposición",
  handoff: "Transferencia clínica",
};

const stateLabels: Record<string, string> = {
  awaiting_confirmation: "Requiere confirmación",
  confirmed: "Confirmada",
  dispatched: "Enviada",
  accepted: "Recibida",
  in_progress: "En ejecución",
  completed: "Completada",
  cancelled: "Cancelada",
  failed: "Sin conexión",
};

const demoScenarios = [
  {
    label: "Trauma multilingüe",
    patient: "I fell from a ladder. My chest hurts and I cannot breathe well.",
    physician:
      "Paciente con dolor torácico y dificultad respiratoria tras caída. Pulso, activar equipo de trauma y solicitar radiografía portátil de tórax.",
  },
  {
    label: "Código ictus",
    patient: "Mi brazo derecho se quedó sin fuerza y me cuesta hablar.",
    physician:
      "Déficit neurológico focal de inicio súbito. Pulso, activar equipo Código Ictus y solicitar tomografía simple de cráneo.",
  },
  {
    label: "Alerta de sepsis",
    patient: "Tengo fiebre, escalofríos y me siento confundido desde anoche.",
    physician:
      "Hipotensión y alteración del estado mental con sospecha de infección. Pulso, activar equipo de sepsis y solicitar laboratorio urgente.",
  },
];

function payloadText(payload: Json): string {
  return Object.entries(payload)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`)
    .join(" · ");
}

function shortTime(value: string): string {
  return new Intl.DateTimeFormat("es-PA", { hour: "2-digit", minute: "2-digit" }).format(
    new Date(value),
  );
}

function blockText(block: Json): string {
  for (const key of ["text", "content", "value"]) {
    if (typeof block[key] === "string" && block[key]) return block[key];
  }
  return JSON.stringify(block);
}

function Logo() {
  return (
    <div className="logo">
      <span className="logo-mark"><HeartPulse size={21} strokeWidth={2.4} /></span>
      <span>PULSO</span>
    </div>
  );
}

function StatusDot({ tone = "mint" }: { tone?: "mint" | "amber" | "red" }) {
  return <span className={`status-dot ${tone}`} />;
}

function App() {
  const [demo, setDemo] = useState(true);
  const [patient, setPatient] = useState("DEMO-001");
  const [bed, setBed] = useState("Trauma 2");
  const [clinician, setClinician] = useState("dra.rivera");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [input, setInput] = useState("");
  const [speaker, setSpeaker] = useState("physician");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [selectedScenario, setSelectedScenario] = useState(0);
  const [demoGuideOpen, setDemoGuideOpen] = useState(false);
  const [ragOpen, setRagOpen] = useState(false);
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState<RagResult[]>([]);
  const [documentBlocks, setDocumentBlocks] = useState<Json[]>([]);
  const [recording, setRecording] = useState(false);
  const [signatureOrder, setSignatureOrder] = useState<Order | null>(null);
  const [signature, setSignature] = useState("dra.rivera / firma local");
  const [exportPath, setExportPath] = useState("");
  const audioSession = useRef<AudioSession | null>(null);

  const encounter = snapshot?.encounter;
  const isCritical = encounter?.state === "critical";
  const latestEvents = useMemo(
    () => [...(snapshot?.events || [])].reverse(),
    [snapshot?.events],
  );

  useEffect(() => {
    setSignature(`${clinician} / firma local`);
  }, [clinician]);

  async function call<T>(payload: Json, label = "Procesando localmente"): Promise<T> {
    setBusy(label);
    setMessage("");
    try {
      return await window.pulso.request<T>({ ...payload, demo });
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      setMessage(text);
      throw error;
    } finally {
      setBusy("");
    }
  }

  async function startEncounter() {
    if (demo) await call({ action: "reset_demo" }, "Preparando entorno de demostración");
    const result = await call<Snapshot>(
      { action: "start", patient_ref: patient, bed, clinician_id: clinician },
      "Iniciando atención local",
    );
    setSnapshot(result);
  }

  function loadScenario(index: number) {
    setSelectedScenario(index);
    setInput(demoScenarios[index].patient);
    setSpeaker("patient");
  }

  async function captureText(text = input, role = speaker) {
    if (!encounter || !text.trim()) return;
    const result = await call<Snapshot>(
      {
        action: "capture_text",
        encounter_id: encounter.id,
        text,
        speaker: role,
        language: role === "physician" ? "es" : "auto",
        actor: clinician,
      },
      "MedPsy está estructurando la conversación",
    );
    setSnapshot(result);
    setInput("");
  }

  async function toggleRecording() {
    try {
      if (recording && audioSession.current) {
        const session = audioSession.current;
        session.processor.disconnect();
        session.source.disconnect();
        session.stream.getTracks().forEach((track) => track.stop());
        await session.context.close();
        audioSession.current = null;
        setRecording(false);
        if (!session.chunks.length) throw new Error("El micrófono no capturó audio");
        const bytes = encodeWav(session.chunks, session.context.sampleRate);
        const path = await window.pulso.saveRecording(bytes, "wav");
        if (!encounter) return;
        const result = await call<Snapshot>(
          {
            action: "capture_audio",
            encounter_id: encounter.id,
            audio_path: path,
            actor: clinician,
          },
          "Whisper, Sortformer y MedPsy procesan el audio",
        );
        setSnapshot(result);
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      processor.onaudioprocess = (event) =>
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      source.connect(processor);
      processor.connect(context.destination);
      audioSession.current = { context, stream, source, processor, chunks };
      setRecording(true);
    } catch (error) {
      const session = audioSession.current;
      if (session) {
        session.processor.disconnect();
        session.source.disconnect();
        session.stream.getTracks().forEach((track) => track.stop());
        if (session.context.state !== "closed") await session.context.close();
      }
      audioSession.current = null;
      setRecording(false);
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function importDocument() {
    if (!encounter) return;
    const path = await window.pulso.pickDocument();
    if (!path) return;
    const result = await call<{ blocks: Json[]; snapshot: Snapshot }>(
      { action: "import_document", encounter_id: encounter.id, path, actor: clinician },
      "OCR local leyendo el documento",
    );
    setSnapshot(result.snapshot);
    setDocumentBlocks(result.blocks);
    setMessage(`${result.blocks.length} bloques detectados y pendientes de revisión`);
  }

  async function importDemoDocument() {
    if (!encounter) return;
    const canvas = document.createElement("canvas");
    canvas.width = 1400;
    canvas.height = 900;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("No fue posible crear el documento de demostración");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#111827";
    context.font = "700 48px Arial";
    context.fillText("DOCUMENTO CLÍNICO SINTÉTICO", 90, 110);
    context.font = "28px Arial";
    [
      "Paciente: DEMO-001",
      "Fecha: 10 de septiembre de 2026",
      "Antecedente: asma",
      "Alergia documentada: penicilina",
      "Motivo: dolor torácico posterior a caída",
      "Uso exclusivo para demostración. Sin datos reales.",
    ].forEach((line, index) => context.fillText(line, 90, 220 + index * 90));
    const blob = await new Promise<Blob>((resolveBlob, rejectBlob) => {
      canvas.toBlob((value) => {
        if (value) resolveBlob(value);
        else rejectBlob(new Error("No fue posible generar la imagen"));
      }, "image/png");
    });
    const path = await window.pulso.saveDemoDocument(
      new Uint8Array(await blob.arrayBuffer()),
    );
    const result = await call<{ blocks: Json[]; snapshot: Snapshot }>(
      { action: "import_document", encounter_id: encounter.id, path, actor: clinician },
      "OCR leyendo el documento sintético",
    );
    setSnapshot(result.snapshot);
    setDocumentBlocks(result.blocks);
    setMessage(`${result.blocks.length} bloques sintéticos detectados y pendientes de revisión`);
  }

  async function playSpeech(utterance: Utterance) {
    const text = utterance.translated_text || utterance.original_text;
    const language = utterance.translated_text ? "es" : utterance.language;
    const result = await call<{ output: string }>(
      { action: "speak", text, language },
      "Preparando lectura en voz alta",
    );
    const bytes = Uint8Array.from(await window.pulso.readRuntimeAudio(result.output));
    const url = URL.createObjectURL(new Blob([bytes.buffer], { type: "audio/wav" }));
    const audio = new Audio(url);
    audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
    await audio.play();
  }

  async function confirmOrder() {
    if (!encounter || !signatureOrder) return;
    let result = await call<Snapshot>(
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
      for (const delay of [800, 1150, 1400]) {
        await new Promise((resolveDelay) => setTimeout(resolveDelay, delay));
        result = await call<Snapshot>(
          { action: "simulate_step", encounter_id: encounter.id, order_id: orderId },
          "El hospital simulado actualiza la orden",
        );
        setSnapshot(result);
      }
    }
  }

  async function cancelOrder(order: Order) {
    if (!encounter) return;
    const result = await call<Snapshot>({
      action: "order_cancel",
      encounter_id: encounter.id,
      order_id: order.id,
      actor: clinician,
    });
    setSnapshot(result);
  }

  async function activateCritical() {
    if (!encounter) return;
    const result = await call<Snapshot>({
      action: "critical",
      encounter_id: encounter.id,
      actor: clinician,
    });
    setSnapshot(result);
  }

  async function searchRag() {
    if (!ragQuery.trim()) return;
    const result = await call<{ results: RagResult[] }>(
      {
        action: "rag_search",
        encounter_id: encounter?.id,
        query: ragQuery,
        actor: clinician,
      },
      "EmbeddingGemma busca evidencia local",
    );
    setRagResults(result.results || []);
  }

  async function closeEncounter() {
    if (!encounter) return;
    const result = await call<{ snapshot: Snapshot; export_path: string }>(
      { action: "close", encounter_id: encounter.id, actor: clinician, signature },
      "Firmando nota y exportando FHIR",
    );
    setSnapshot(result.snapshot);
    setExportPath(result.export_path);
  }

  if (!snapshot) {
    return (
      <div className="onboarding-shell">
        <div className="ambient one" />
        <div className="ambient two" />
        <header className="onboarding-nav">
          <Logo />
        </header>
        <main className="onboarding">
          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            className="hero-copy"
          >
            <h1>PULSO</h1>
            <p>
              Captura los hechos relevantes de la atención y coordina órdenes clínicas desde
              una sola interfaz.
            </p>
          </motion.section>
          <motion.section
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.08 }}
            className="start-card"
          >
            <div className="card-heading">
              <div>
                <span className="section-kicker">Nueva atención</span>
                <h2>Preparar cubículo</h2>
              </div>
              <Stethoscope size={24} />
            </div>
            <label>Referencia del paciente<input value={patient} onChange={(event) => setPatient(event.target.value)} /></label>
            <div className="field-grid">
              <label>Cubículo<input value={bed} onChange={(event) => setBed(event.target.value)} /></label>
              <label>Profesional<input value={clinician} onChange={(event) => setClinician(event.target.value)} /></label>
            </div>
            <div className="demo-switch">
              <div>
                <strong>Entorno de demostración</strong>
                <small>Datos sintéticos y respuestas hospitalarias simuladas</small>
              </div>
              <button className={demo ? "switch active" : "switch"} onClick={() => setDemo(!demo)} aria-label="Modo demo"><span /></button>
            </div>
            <button className="primary wide" onClick={startEncounter} disabled={Boolean(busy)}>
              <span>Iniciar atención</span><ArrowUpRight size={18} />
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
        <nav>
          <button className="nav-item active"><Activity size={19} /><span>Atención</span></button>
          <button className="nav-item" onClick={() => setRagOpen(true)}><Search size={19} /><span>Evidencia</span></button>
          <button className="nav-item" onClick={importDocument}><FileScan size={19} /><span>Documentos</span></button>
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <LockKeyhole size={17} />
            <div><strong>Procesamiento local</strong><small>Ningún dato sale del equipo</small></div>
          </div>
          <div className="profile"><span>{clinician.slice(0, 2).toUpperCase()}</span><div><strong>{clinician}</strong><small>Sesión local</small></div></div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="patient-title">
            <div className="patient-avatar"><UserRound size={20} /></div>
            <div><span>{encounter.patient_ref}</span><small>{encounter.bed} · Urgencias</small></div>
            <span className={`encounter-state ${isCritical ? "red" : ""}`}><StatusDot tone={isCritical ? "red" : "mint"} />{isCritical ? "MODO CRÍTICO" : "CAPTURA ACTIVA"}</span>
          </div>
          <div className="top-actions">
            {demo && <span className="demo-label">SIMULACIÓN</span>}
            {demo && <button className="ghost" onClick={() => setDemoGuideOpen(true)}><BookOpenCheck size={17} /> Guía demo</button>}
            <button className="ghost danger" onClick={activateCritical}><AlertTriangle size={17} /> Modo crítico</button>
            <button className="ghost" onClick={closeEncounter} disabled={encounter.state === "closed"}><BadgeCheck size={17} /> Finalizar</button>
          </div>
        </header>

        <div className="clinical-grid">
          <section className="conversation-panel">
            <div className="panel-header">
              <div><span className="section-kicker">Línea temporal</span><h2>Historia clínica en vivo</h2></div>
              <button className="icon-button" onClick={() => setRagOpen(true)} title="Consultar evidencia"><Search size={18} /></button>
            </div>
            <div className="timeline">
              {snapshot.utterances.length > 0 && (
                <section className="utterance-list">
                  {[...snapshot.utterances].slice(-4).map((utterance) => (
                    <article key={utterance.id}>
                      <div><strong>{utterance.speaker === "physician" ? "Profesional" : "Paciente / interlocutor"}</strong><span>{utterance.language.toUpperCase()}</span></div>
                      <p>{utterance.original_text}</p>
                      {utterance.translated_text && <small>ES · {utterance.translated_text}</small>}
                      <button onClick={() => void playSpeech(utterance)} title="Escuchar"><Volume2 size={14} /></button>
                    </article>
                  ))}
                </section>
              )}
              {documentBlocks.length > 0 && (
                <section className="document-preview">
                  <div><FileScan size={15} /><strong>Documento incorporado</strong><span>{documentBlocks.length} bloques</span></div>
                  {documentBlocks.slice(0, 3).map((block, index) => <p key={index}>{blockText(block)}</p>)}
                </section>
              )}
              {latestEvents.length === 0 ? (
                <div className="empty-state"><Activity size={28} /><h3>Escuchando el contexto clínico</h3><p>Los hechos relevantes aparecerán aquí. La conversación irrelevante no se guarda como evento.</p></div>
              ) : latestEvents.map((event, index) => (
                <motion.article
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  key={event.id}
                  className="timeline-event"
                >
                  <div className={`event-node ${event.actionable ? "action" : ""}`}>{event.actionable ? <Radio size={14} /> : <Check size={14} />}</div>
                  <div className="event-body">
                    <div><strong>{eventLabels[event.type] || event.type}</strong><time>{shortTime(event.created_at)}</time></div>
                    <p>{payloadText(event.payload)}</p>
                    <div className="event-meta"><span>{event.state.replaceAll("_", " ")}</span>{event.confidence != null && <span>{Math.round(event.confidence * 100)}% confianza</span>}</div>
                  </div>
                  {index < latestEvents.length - 1 && <span className="event-line" />}
                </motion.article>
              ))}
            </div>
            <div className="composer">
              {demo && (
                <div className="scenario-row">
                  <span>Caso:</span>
                  {demoScenarios.map((scenario, index) => (
                    <button key={scenario.label} className={selectedScenario === index ? "selected" : ""} onClick={() => loadScenario(index)}>{scenario.label}</button>
                  ))}
                </div>
              )}
              <div className="speaker-tabs">
                <button className={speaker === "patient" ? "active" : ""} onClick={() => setSpeaker("patient")}>Paciente</button>
                <button className={speaker === "physician" ? "active" : ""} onClick={() => setSpeaker("physician")}>Profesional</button>
              </div>
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Habla con naturalidad. Para una orden explícita, comienza con “Pulso…”"
              />
              <div className="composer-footer">
                <div className="capture-tools">
                  <button className={recording ? "record-button active" : "record-button"} onClick={toggleRecording}>{recording ? <CircleStop size={18} /> : <Mic size={18} />}{recording ? "Detener" : "Grabar"}</button>
                  <button className="tool-button" onClick={importDocument}><FileScan size={17} /> OCR</button>
                  {demo && <button className="tool-button" onClick={importDemoDocument}><FileScan size={17} /> Documento demo</button>}
                  <button className="tool-button" onClick={() => setRagOpen(true)}><Languages size={17} /> Evidencia</button>
                </div>
                <button className="send-button" onClick={() => captureText()} disabled={!input.trim() || Boolean(busy)}><Send size={18} /></button>
              </div>
              {demo && speaker === "patient" && input === "" && (
                <button className="next-demo" onClick={() => { setSpeaker("physician"); setInput(demoScenarios[selectedScenario].physician); }}>
                  Preparar intervención del médico <ChevronRight size={16} />
                </button>
              )}
            </div>
          </section>

          <aside className="orders-panel">
            <div className="panel-header">
              <div><span className="section-kicker">Lazo cerrado</span><h2>Coordinación</h2></div>
              <span className="count-badge">{snapshot.orders.length}</span>
            </div>
            <div className="orders-list">
              {snapshot.orders.length === 0 ? (
                <div className="orders-empty"><Radio size={24} /><p>Las órdenes explícitas aparecerán aquí para revisión y firma.</p></div>
              ) : snapshot.orders.map((order) => {
                const isDone = order.state === "completed";
                const isCancelled = order.state === "cancelled";
                const simulated = snapshot.transitions.some((item) => item.order_id === order.id && item.actor.startsWith("demo."));
                return (
                  <motion.article layout key={order.id} className={`order-card ${isDone ? "done" : ""}`}>
                    <div className="order-top"><span className="destination"><Radio size={14} />{order.destination}</span>{simulated && <span className="simulated">SIMULADO</span>}</div>
                    <h3>{order.request}</h3>
                    <div className="order-state"><span className={`order-state-icon ${order.state}`}>{isDone ? <Check size={13} /> : isCancelled ? <X size={13} /> : <Activity size={13} />}</span><strong>{stateLabels[order.state] || order.state}</strong></div>
                    {order.state === "awaiting_confirmation" && (
                      <div className="order-actions"><button className="confirm" onClick={() => setSignatureOrder(order)}>Revisar y firmar</button><button className="cancel" onClick={() => cancelOrder(order)}><XCircle size={16} /></button></div>
                    )}
                    {!["awaiting_confirmation", "completed", "cancelled"].includes(order.state) && (
                      <div className="progress-track"><span className={`progress-fill ${order.state}`} /></div>
                    )}
                  </motion.article>
                );
              })}
            </div>
            <div className="quick-call">
              <span>Comandos rápidos</span>
              <div>
                {["Código Azul", "Equipo de Trauma", "Código Ictus", "Sepsis"].map((team) => (
                  <button key={team} onClick={() => { setSpeaker("physician"); setInput(`Pulso, activar ${team}.`); }}>{team}</button>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </main>

      <AnimatePresence>
        {busy && (
          <motion.div className="busy-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="busy-card"><span className="pulse-ring"><BrainCircuit size={24} /></span><strong>{busy}</strong></div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {demoGuideOpen && (
          <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setDemoGuideOpen(false)}>
            <motion.aside className="demo-drawer" initial={{ x: 470 }} animate={{ x: 0 }} exit={{ x: 470 }} transition={{ type: "spring", damping: 28, stiffness: 280 }} onClick={(event) => event.stopPropagation()}>
              <div className="drawer-header"><div><span className="section-kicker">Recorrido completo</span><h2>Demostración guiada</h2></div><button className="icon-button" onClick={() => setDemoGuideOpen(false)}><X size={18} /></button></div>
              <p className="drawer-intro">Usa el micrófono o carga cada frase en el editor. La transcripción, traducción, extracción, OCR y búsqueda son reales; solo las respuestas de las áreas hospitalarias están simuladas y se identifican en pantalla.</p>
              <ol className="demo-steps">
                <li><strong>Paciente en inglés</strong><p>“I fell from a ladder. My chest hurts and I cannot breathe well.”</p><button onClick={() => { setSpeaker("patient"); setInput(demoScenarios[0].patient); setDemoGuideOpen(false); }}>Cargar frase</button></li>
                <li><strong>Valoración y orden</strong><p>“Paciente con dolor torácico y dificultad respiratoria tras caída. Pulso, activar equipo de trauma y solicitar radiografía portátil de tórax.”</p><button onClick={() => { setSpeaker("physician"); setInput(demoScenarios[0].physician); setDemoGuideOpen(false); }}>Cargar frase</button></li>
                <li><strong>Lazo cerrado</strong><p>Revisa, firma y observa la recepción, ejecución y finalización simuladas.</p></li>
                <li><strong>OCR</strong><p>Usa “Documento demo” para generar y leer una nota clínica completamente sintética.</p><button onClick={() => { setDemoGuideOpen(false); void importDemoDocument(); }}>Procesar documento</button></li>
                <li><strong>Evidencia</strong><p>Busca “¿Qué elementos debe incluir una transferencia segura de un paciente traumatizado?”</p><button onClick={() => { setRagQuery("¿Qué elementos debe incluir una transferencia segura de un paciente traumatizado?"); setDemoGuideOpen(false); setRagOpen(true); }}>Abrir búsqueda</button></li>
                <li><strong>Cierre</strong><p>Activa el modo crítico para mostrar continuidad operativa y finaliza para generar la nota firmada y el paquete FHIR.</p></li>
              </ol>
              <div className="live-note"><Mic size={17} /><div><strong>Demo en vivo</strong><p>Pulsa Grabar, di una frase completa y pulsa Detener. PULSO reacciona al terminar cada intervención.</p></div></div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {signatureOrder && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal" initial={{ scale: 0.97, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, y: 10 }}>
              <button className="modal-close" onClick={() => setSignatureOrder(null)}><X size={18} /></button>
              <span className="modal-icon"><ShieldCheck size={22} /></span>
              <span className="section-kicker">Confirmación clínica</span>
              <h2>Revisar antes de enviar</h2>
              <div className="readback"><small>Destino</small><strong>{signatureOrder.destination}</strong><p>{signatureOrder.request}</p></div>
              <label>Firma local del profesional<input value={signature} onChange={(event) => setSignature(event.target.value)} /></label>
              <p className="safety-copy">PULSO no ejecutará esta orden hasta que confirmes que el contenido y el destino son correctos.</p>
              <button className="primary wide" onClick={confirmOrder}>Confirmar y enviar <Send size={17} /></button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {ragOpen && (
          <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setRagOpen(false)}>
            <motion.aside className="rag-drawer" initial={{ x: 440 }} animate={{ x: 0 }} exit={{ x: 440 }} transition={{ type: "spring", damping: 28, stiffness: 280 }} onClick={(event) => event.stopPropagation()}>
              <div className="drawer-header"><div><span className="section-kicker">RAG local</span><h2>Evidencia operativa</h2></div><button className="icon-button" onClick={() => setRagOpen(false)}><X size={18} /></button></div>
              <p className="drawer-intro">Consulta las fuentes descargadas en el equipo. Los resultados apoyan la revisión; no sustituyen el criterio clínico.</p>
              <div className="rag-search"><Search size={18} /><input value={ragQuery} onChange={(event) => setRagQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void searchRag(); }} placeholder="Ej.: campos para transferencia aguda" /><button onClick={searchRag}>Buscar</button></div>
              <div className="rag-results">
                {ragResults.map((result, index) => (
                  <article key={index}><div><span>Fuente {index + 1}</span>{result.score != null && <small>{Math.round(result.score * 100)}% relevancia</small>}</div><p>{String(result.content || result.text || "Resultado local")}</p></article>
                ))}
                {ragResults.length === 0 && <div className="rag-empty"><Search size={25} /><p>Los fragmentos recuperados mostrarán su fuente y localizador.</p></div>}
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      {message && <button className="toast" onClick={() => setMessage("")}><span>{message}</span><X size={15} /></button>}
      {exportPath && <div className="export-toast"><BadgeCheck size={17} /><span>Atención cerrada · FHIR guardado en {exportPath}</span></div>}
    </div>
  );
}

export default App;
