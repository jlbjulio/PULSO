# PULSO | Copiloto de operaciones clínicas

PULSO ayuda al personal de urgencias a documentar una atención y coordinar solicitudes sin apartar la vista del paciente. Escucha la conversación en el equipo local, conserva los hechos clínicos relevantes y distingue una posibilidad discutida de una orden confirmada.

## Uso durante una atención

1. El médico abre el paciente correcto e inicia la captura.
2. Whisper detecta el habla y Sortformer separa las voces presentes.
3. MedPsy convierte los fragmentos útiles en eventos con hora, hablante y evidencia.
4. Una instrucción como `Pulso, solicitar radiografía portátil de tórax` crea un borrador.
5. PULSO lee la solicitud. El médico la confirma y firma desde su sesión.
6. El área receptora actualiza el estado hasta completar, cancelar o reemplazar la orden.
7. Al terminar, el médico revisa y firma la documentación clínica.

La pantalla mantiene a la vista el paciente activo, los eventos recientes, las órdenes pendientes y el estado de la conexión. Si el audio se mezcla con otra camilla o pierde el encuentro activo, la captura automática se detiene y el flujo manual sigue disponible.

## Eventos y órdenes

PULSO registra síntomas, alergias, antecedentes, hallazgos expresados, diagnósticos documentados, intervenciones, medicamentos, resultados y correcciones. Cada dato conserva el fragmento de audio, texto o documento que lo originó.

Una orden puede estar `considerada`, en `borrador`, `confirmada`, `aceptada`, `en ejecución`, `completada`, `cancelada` o `reemplazada`. Mencionar una dosis no demuestra que fue administrada. El estado `administrado` exige una declaración explícita del equipo.

El comando `Pulso` puede dirigir solicitudes a imagenología, laboratorio, farmacia, banco de sangre, transporte, especialistas y equipos de respuesta configurados por el hospital. Cada orden tiene un identificador estable para evitar duplicados durante un reintento. Los retrasos siguen el tiempo y la ruta de escalamiento definidos por el centro.

## Idiomas, documentos y fuentes clínicas

Cuando el paciente habla un idioma compatible, TranslatePsy genera una traducción de trabajo al español y Supertonic puede reproducirla. El texto original siempre queda visible. Los casos de alto riesgo requieren un intérprete según la política del hospital.

OCR Latin lee recetas, referencias e informes fotografiados. Cada dato extraído queda unido a la región de la imagen para que el médico pueda comprobarlo antes de incorporarlo.

El RAG local se activa cuando el médico pide una verificación o una regla marca un dato para revisión. Busca fragmentos dentro de protocolos aprobados y muestra su fuente y versión. La recuperación nunca crea una orden, una dosis o un diagnóstico. El médico evalúa, diagnostica, decide y firma.

## Modo crítico

Durante una reanimación, PULSO registra una línea temporal candidata y silencia preguntas que puedan distraer. La conciliación se realiza cuando el equipo indica un momento seguro. Los sistemas oficiales del hospital siguen siendo la vía principal para alarmas y convocatorias.

## Modelos

| Función | Modelo |
| --- | --- |
| Extracción clínica | MedPsy 4B Q4_K_M con *imatrix* |
| Transcripción | Whisper Small Q8 + Silero VAD |
| Separación de voces | Sortformer 4SPK v2.1 Q4 |
| Traducción | TranslatePsy EuroNano + AfriNano |
| Documentos | OCR Latin |
| Fuentes clínicas | EmbeddingGemma 300M Q4 + RAG de QVAC |
| Voz | Supertonic 3 Q4 |

Los modelos se cargan según la tarea para trabajar dentro de los 4 GB de VRAM disponibles. Audio, documentos, índices y pesos permanecen en la infraestructura local. No hay fallback de inferencia en la nube.

## Entorno

El equipo preparado tiene Python 3.11, Node.js 24, QVAC SDK 0.19.0, QVAC CLI 0.13.0, Flet 0.86.5, FFmpeg 9 y los modelos descargados. No crea ni utiliza `.venv`.

Los pesos están organizados en `models/` y sus rutas se encuentran en `config/models.json`. Las fuentes clínicas de `data/rag/fuentes/` se distribuyen con el repositorio; únicamente los pesos permanecen fuera de Git.

```console
python tools/prepare_environment.py
```

Para ejecutar el fine-tuning LoRA cuando corresponda:

```console
python training/train_lora.py
```

## Estructura

```text
pulso-qvac/
├── assets/              Recursos de la interfaz
├── config/              Servicios, permisos y códigos del hospital
├── data/                Evaluación, fine-tuning y fuentes clínicas
├── migrations/          Cambios de SQLite
├── models/              Pesos locales de QVAC
├── schemas/             Contratos de eventos
├── training/            Fine-tuning LoRA y resultados locales
├── src/pulso/
│   ├── application/     Casos de uso y coordinación
│   ├── domain/          Eventos, órdenes y reglas
│   ├── infrastructure/  QVAC, SQLite, P2P y enrutamiento
│   └── ui/              Vistas y componentes Flet
└── tests/               Pruebas y fixtures
```

## Tecnologías y atribuciones

QVAC CLI, los clientes JS/Python y los modelos QVAC pertenecen a Tether. Las fuentes de WHO, MINSA Panamá y HL7 están identificadas en `data/rag/manifest.json`. Las dependencias conservan versiones fijas en los archivos del repositorio.

La base preexistente fue preparada por Julio Lara e incluye esta estructura, las dependencias, contratos de eventos, datos sintéticos y pruebas de esos datos. El repositorio contiene la base técnica QVAC. No contiene la aplicación clínica funcional ni integraciones hospitalarias terminadas.
