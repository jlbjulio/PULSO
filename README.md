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

## IA local y modelos

Las operaciones principales de inferencia y RAG se implementarán con `@qvac/sdk` 0.19.0 y modelos locales. TranslatePsy utiliza el runtime local `@qvac/translation-nmtcpp`. No existe fallback hacia APIs de inferencia en la nube.

| Función | Modelo y cuantización |
| --- | --- |
| Extracción de eventos | `qvac/MedPsy-4B-GGUF` — `medpsy-4b-q4_k_m-imat.gguf` |
| Traducción | `qvac/TranslatePsy-EuroNano` y `qvac/TranslatePsy-AfriNano` — INTGEMM |
| Transcripción | Whisper Small Q8_0 + Silero VAD 5.1.2 |
| Separación de voces | Sortformer 4SPK v2.1 Q4_0 |
| Documentos | OCR Latin G2 + detector CRAFT |
| RAG local | EmbeddingGemma 300M Q4_0 |
| Voz | Supertonic 3 Q4_0 |

MedPsy es el modelo Psy central: transforma únicamente evidencia explícita en eventos clínicos estructurados. TranslatePsy participa cuando existe una barrera de idioma. Los modelos se cargan según la tarea para respetar los 4 GB de VRAM del equipo de demostración.

## Seguridad y limitaciones

PULSO es un prototipo de apoyo operativo, no un sistema autónomo de diagnóstico ni un dispositivo médico validado. No prescribe, no decide tratamientos y no ejecuta órdenes por sí solo. Toda orden exige intención explícita, confirmación de lazo cerrado, identidad profesional y firma. Una salida incierta conserva la evidencia y pasa a revisión humana.

El sistema no sustituye los canales oficiales de emergencia, los protocolos del hospital ni a un intérprete clínico cuando sea necesario. La demostración utiliza datos sintéticos y no incluye información real de pacientes.

## Entorno reproducible

- Windows 11 Home Single Language 10.0.26200.
- AMD Ryzen 7 5800H, 15.3 GB de RAM y NVIDIA RTX 3050 Laptop de 4 GB.
- Node.js 24, npm 11, Python 3.11, QVAC SDK 0.19.0 y QVAC CLI 0.13.0.
- Sin entornos virtuales de Python.

```console
python tools/prepare_environment.py
```

Los pesos se descargan y verifican mediante `tools/download-models.js`, se almacenan en `models/` y permanecen fuera de Git. Las rutas esperadas están declaradas en `config/models.json`.

## Datos y componentes externos

- Los conjuntos SFT contienen 285 casos de entrenamiento, 57 de validación y 57 de prueba; todos son sintéticos y no entrenan decisiones clínicas.
- Las fuentes de WHO, MINSA Panamá y HL7 se identifican individualmente en `data/rag/manifest.json` y `data/rag/fuentes.csv`.
- QVAC SDK, QVAC CLI, los modelos QVAC/Tether, Flet, PyMuPDF, Pydantic, FFmpeg, TensorBoard y las demás dependencias conservan sus licencias y atribuciones originales.
- La licencia MIT cubre únicamente el código propio de PULSO; los documentos, modelos y demás materiales de terceros conservan sus términos originales.
- No se utilizan APIs remotas de IA. Cualquier servicio remoto futuro, incluso si no realiza inferencia, deberá declararse aquí.

## Base preexistente

El proyecto partió de los siguientes elementos preexistentes:

| Elemento | Origen | Uso |
| --- | --- | --- |
| Repositorio inicial  | Julio Lara | `.gitignore`, licencia y README inicial |
| Preparación técnica  | Julio Lara | Arquitectura de carpetas, stubs Python, configuración, dependencias, herramientas de entorno y descarga, esquemas, pruebas, corpus RAG, casos sintéticos y script de preparación LoRA |
| Fuentes clínicas y técnicas | WHO, MINSA Panamá y HL7 | Corpus local de consulta; origen y ubicación registrados en el manifiesto |
| Modelos locales | QVAC, Tether AI Research y registro oficial del SDK | Preparación del equipo; pesos excluidos de Git |

La base anterior no contenía una aplicación clínica funcional: los módulos de `src/pulso/` eran stubs sin implementación y no existían integraciones hospitalarias terminadas. Toda base adicional incorporada se añadirá a esta declaración.
