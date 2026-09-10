# PULSO

PULSO es un copiloto de operaciones clínicas para salas de urgencias. Escucha la atención, conserva únicamente los hechos relevantes, traduce cuando existe una barrera de idioma y coordina órdenes clínicas mediante comandos de voz, revisión y firma profesional.

## Funcionamiento

1. El profesional abre una atención por cubículo. El paciente recibe una referencia provisional que puede actualizarse cuando sea identificado.
2. En operación normal, el micrófono permanece activo. Whisper transcribe por fragmentos y Sortformer separa las intervenciones. La conversación completa permanece visible durante la atención, separada del registro clínico relevante.
3. Cuando detecta otro idioma, PULSO lo conserva como idioma del paciente. TranslatePsy traduce al español lo dicho por el paciente y traduce hacia su idioma las respuestas del profesional. Supertonic reproduce estas traducciones dentro de la misma conversación.
4. Cuando detecta una orden, medicamento, activación crítica o traslado, el RAG recupera contexto local de emergencia, seguridad e interoperabilidad. MedPsy utiliza ese contexto para normalizar términos y validar la estructura, sin convertir una fuente externa en un hecho del paciente.
5. MedPsy con el adaptador LoRA de PULSO extrae síntomas, antecedentes, signos vitales, hallazgos, diagnósticos documentados, intervenciones, resultados y órdenes.
6. Solo una instrucción explícita iniciada con `Pulso` crea una orden. El profesional debe revisar y firmar antes de enviarla al equipo, especialista o servicio correspondiente.
7. Al finalizar, PULSO genera un informe clínico de Word únicamente con los hechos relevantes, la identificación, los hallazgos, las órdenes, la cronología clínica y la firma, además de un paquete FHIR R4. Después puede iniciarse una nueva atención.

La demostración incluye casos sintéticos completos y una captura por micrófono bajo demanda. La operación normal utiliza escucha continua.

## Componentes

- `src/app/`: aplicación de escritorio Electron y React.
- `src/pulso/clinical/`: atenciones, eventos, seguridad, órdenes e informes.
- `src/pulso/storage/`: SQLite, auditoría, destinos y cola local.
- `src/pulso/ai/`: audio, traducción, RAG y extracción clínica.
- `src/qvac/`: inferencia local mediante `@qvac/sdk`.
- `training/`: entrenamiento y evaluación del adaptador LoRA.
- `data/`: corpus RAG, evaluación y datos sintéticos de fine-tuning.

## Modelos

| Función | Modelo |
| --- | --- |
| Extracción clínica | `qvac/MedPsy-1.7B-GGUF`, Q8_0, con LoRA de PULSO |
| Transcripción | Whisper Small Q8_0 y Silero VAD 5.1.2 |
| Diarización | Sortformer 4SPK v2.1 Q4_0 |
| RAG | EmbeddingGemma 300M Q4_0 |
| Traducción | `qvac/TranslatePsy-EuroNano`, INTGEMM |
| Voz | Supertonic 3 Q4_0 |
| Preparación de fuentes escaneadas | OCR Latin G2 y CRAFT |

MedPsy, Whisper, Sortformer, EmbeddingGemma, las dos direcciones de TranslatePsy y los idiomas configurados de Supertonic se cargan una sola vez antes de mostrar la aplicación y permanecen disponibles durante la sesión. Traducción y voz solo ejecutan inferencia cuando el caso lo requiere. Toda la inferencia principal y el RAG se ejecutan localmente mediante QVAC; no se utilizan APIs de inferencia remota.

Cada ejecución registra modelo, cuantización, carga, prompt, tokens, TTFT, latencia y throughput en `runtime-data/performance.jsonl`.

## Instalación

Requiere Windows 11, Python 3.11 o superior, Node.js 22.17 o superior y aproximadamente 12 GB libres. El proyecto utiliza la instalación principal de Python, sin entorno virtual. El hardware de referencia es un AMD Ryzen 7 5800H, 15.3 GB de RAM y una NVIDIA RTX 3050 Laptop de 4 GB.

```console
python tools/prepare_environment.py
```

El comando instala dependencias, descarga los modelos, prepara las fuentes, crea el índice RAG y configura la base local. Para abrir PULSO:

```console
npm run app
```

La aplicación espera la carga de todos los modelos antes de mostrar la ventana y evita recargarlos entre acciones durante la sesión.

## Entrenamiento

El conjunto SFT contiene 42 casos de entrenamiento, 10 de validación y 69 de prueba. Todos son sintéticos y están diseñados para distinguir hechos, negaciones, correcciones, acciones realizadas, ideas consideradas y comandos explícitos.

```console
npm run train
npm run train:evaluate
```

El entrenamiento se realiza localmente. TensorBoard queda disponible en `http://127.0.0.1:6006` y el adaptador final se guarda en `training/output/pulso-medpsy-lora.gguf`.

## Verificación

```console
npm run check
```

La validación del micrófono y del flujo clínico completo debe realizarse manualmente desde la aplicación con datos sintéticos.

## Seguridad y limitaciones

PULSO es una herramienta de apoyo operativo y no es un dispositivo médico validado. No diagnostica, prescribe ni ejecuta órdenes de forma autónoma. Una posibilidad discutida no se registra como una acción realizada y una mención de medicamento no equivale a su administración. Toda orden requiere intención explícita, revisión, identidad y firma profesional.

Las salidas inciertas permanecen sujetas a revisión. El sistema no sustituye el criterio clínico, los protocolos hospitalarios, los canales oficiales de emergencia ni los servicios de interpretación profesional.

## Datos, licencias y base preexistente

El código propio se distribuye bajo MIT. Los modelos, fuentes y componentes de terceros conservan sus licencias originales. `data/rag/manifest.json` registra origen, URL, checksum, atribución y estado de inclusión; `data/rag/sources.csv` enumera el corpus activo.

El corpus activo contiene 45 publicaciones de WHO, 7 definiciones de HL7 FHIR y 2 textos legales oficiales de Panamá. El índice se genera localmente y omite correos y teléfonos detectables durante la extracción.

La base preexistente estaba compuesta por el repositorio inicial, licencia, estructura, configuración de modelos, esquemas, scripts de preparación y descarga, manifiesto de fuentes y conjuntos sintéticos preparados por Julio Lara. Los documentos proceden de WHO, HL7 y fuentes oficiales de Panamá; los pesos locales proceden de QVAC, Tether AI Research y el registro de modelos del SDK.
