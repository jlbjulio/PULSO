# PULSO

PULSO es un copiloto local de operaciones clínicas para salas de urgencias. Convierte conversaciones y documentos en una línea temporal verificable, mantiene separadas las decisiones consideradas de las acciones realizadas y coordina órdenes mediante confirmación y firma profesional.

La inferencia y el RAG se ejecutan en el dispositivo con QVAC. El audio, los documentos y los datos clínicos no se envían a servicios de IA remotos.

## Flujo de uso

1. El profesional inicia una atención y activa la escucha.
2. Whisper transcribe el audio, Sortformer separa voces y MedPsy extrae únicamente hechos clínicos respaldados por la conversación.
3. TranslatePsy ayuda cuando existe una barrera de idioma y Supertonic permite escuchar la traducción. OCR incorpora imágenes y PDF después de revisión humana.
4. Las posibilidades discutidas quedan como consideradas. Solo una instrucción explícita que empiece con `Pulso` puede crear un borrador de orden.
5. El profesional revisa, confirma y firma antes del envío al área correspondiente.
6. PULSO conserva eventos, estados, evidencia, documentos y órdenes en una base local con auditoría encadenada.
7. Al finalizar, genera una nota firmada y un paquete FHIR R4 local.

En modo crítico la captura continúa sin interrumpir la atención y la conciliación queda para un momento seguro.

## Capacidades

- Aplicación de escritorio para Windows construida con Electron, React y TypeScript.
- Captura por micrófono o texto con ASR, diarización y extracción estructurada.
- Órdenes para imagenología, laboratorio, farmacia, procedimientos, transporte, interconsultas y equipos de respuesta.
- Estados de lazo cerrado, firma local, idempotencia, cancelación y cola offline.
- OCR de imágenes y PDF con evidencia por bloque y página.
- Traducción entre español, inglés, portugués, francés, alemán, italiano, neerlandés, finés, checo y sueco.
- Lectura local en voz alta de transcripciones y traducciones.
- RAG local sobre 54 fuentes identificadas de WHO, HL7 y normativa oficial de Panamá.
- Historial auditable mediante hashes SHA-256 y exportación interoperable FHIR R4.
- Registro estructurado de carga, prompts, tokens, TTFT, latencia y throughput en `runtime-data/performance.jsonl`.

## Estructura

- `src/app/`: interfaz React y aplicación de escritorio Electron.
- `src/pulso/clinical/`: eventos, atenciones, órdenes y documentación clínica.
- `src/pulso/storage/`: base local, auditoría, routing y cola de entrega.
- `src/pulso/ai/`: audio, traducción, OCR, RAG y extracción clínica.
- `src/qvac/`: motor TypeScript conectado directamente con `@qvac/sdk`.
- `training/`: preparación, entrenamiento y evaluación del LoRA.
- `data/`: fuentes y corpus RAG, evaluaciones y conjuntos sintéticos.

## Modelos locales

| Función | Modelo |
| --- | --- |
| Extracción clínica | `qvac/MedPsy-1.7B-GGUF`, Q8_0, con adaptador LoRA obligatorio de PULSO |
| Traducción | `qvac/TranslatePsy-EuroNano`, INTGEMM |
| Transcripción | Whisper Small Q8_0 y Silero VAD 5.1.2 |
| Diarización | Sortformer 4SPK v2.1 Q4_0 |
| OCR | OCR Latin G2 y CRAFT |
| RAG | EmbeddingGemma 300M Q4_0 |
| Voz | Supertonic 3 Q4_0 |

MedPsy es el modelo central del flujo principal. Todos los modelos se cargan mediante `@qvac/sdk` 0.19.0 y se descargan bajo `models/`, fuera del control de versiones.

La aplicación no utiliza APIs remotas durante su operación. La red solo interviene durante la preparación inicial para descargar dependencias, modelos y fuentes desde las ubicaciones declaradas.

## Instalación

Requiere Windows 11, Python 3.11 o superior, Node.js 22.17 o superior y aproximadamente 12 GB libres. No se utiliza un entorno virtual de Python. La configuración validada utiliza un AMD Ryzen 7 5800H, 15.3 GB de RAM y una NVIDIA RTX 3050 Laptop de 4 GB.

```console
python tools/prepare_environment.py
```

El instalador descarga dependencias, modelos y fuentes desde sus ubicaciones oficiales, verifica los checksums, crea la base local e indexa el corpus RAG. Para abrir la aplicación:

```console
npm run app
```

Activa `Entorno de demostración` en la pantalla inicial para trabajar con datos sintéticos. `Guía demo` recorre captura por texto o micrófono, traducción, extracción clínica, orden firmada, respuesta del área, OCR, evidencia local, modo crítico y exportación. La inferencia sigue siendo real; únicamente las respuestas de las áreas hospitalarias se simulan y aparecen identificadas en la interfaz.

Para comprobar el repositorio:

```console
npm run check
```

## Entrenamiento local

El conjunto SFT contiene 30 casos de entrenamiento, 10 de validación y 69 de prueba, todos sintéticos. Incluye negativos difíciles para reducir eventos falsos y distinguir la palabra clínica “pulso” del comando de activación. El ajuste LoRA especializa la extracción de hechos, negaciones, correcciones, estados e intención explícita; no entrena recomendaciones clínicas.

```console
npm run train
npm run train:evaluate
```

El entrenamiento se ejecuta localmente y abre TensorBoard en `http://127.0.0.1:6006`. El adaptador anterior se conserva si el proceso falla; solo una ejecución completada reemplaza `training/output/pulso-medpsy-lora.gguf`, que la aplicación carga automáticamente.

## Seguridad y limitaciones

PULSO es una herramienta de apoyo operativo y no es un dispositivo médico validado. No diagnostica, prescribe ni ejecuta órdenes de forma autónoma. Una mención de medicamento no equivale a una administración. Toda orden requiere intención explícita, revisión, identidad y firma profesional.

Las salidas inciertas conservan su evidencia y pasan a revisión. El sistema no sustituye los protocolos, canales oficiales de emergencia ni intérpretes clínicos. Las demostraciones deben utilizar datos sintéticos.

## Datos, licencias y base preexistente

El código propio se distribuye bajo MIT. Los modelos, documentos y componentes de terceros conservan sus licencias originales. El origen, la URL, el checksum y el estado de inclusión de cada fuente están registrados en `data/rag/manifest.json`; `data/rag/sources.csv` enumera el corpus activo.

El corpus utiliza 45 publicaciones de WHO, 7 definiciones base de HL7 FHIR y 2 textos legales oficiales de Panamá. La procedencia, atribución, URL y condiciones aplicables de cada fuente se conservan en el manifiesto. El índice se genera localmente y omite correos y teléfonos detectables durante la extracción.

La base preexistente estaba compuesta por el repositorio inicial, la licencia, la estructura de carpetas, configuración de modelos, esquemas, scripts de preparación y descarga, manifiesto de fuentes y conjuntos sintéticos preparados por Julio Lara. Los documentos proceden de WHO, HL7 y fuentes oficiales de Panamá; los pesos locales proceden de QVAC, Tether AI Research y el registro de modelos del SDK. Esa base no contenía una aplicación clínica funcional ni integraciones hospitalarias terminadas.
