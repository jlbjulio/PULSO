# Registro de rendimiento

El rendimiento se registra en `runtime-data/performance.jsonl`, con una línea JSON por operación.

```json
{
  "timestamp": "2026-09-10T02:40:33.604Z",
  "model": "models/clinical/medpsy-1.7b-q8_0.gguf",
  "prompt": "{\"patient_ref\":\"demo-patient\",\"utterances\":[{\"id\":\"u1\",\"speaker\":\"physician\",\"language\":\"es\",\"text\":\"Pulso, solicitar radiografia de torax portatil por trauma cerrado.\"}]}",
  "model_load_ms": 31276.1607,
  "input_tokens": 209,
  "output_tokens": 160,
  "ttft_ms": 26520.405,
  "tokens_per_second": 19.1232903629
}
```

| Campo | Descripción |
| --- | --- |
| `model_load_ms` | Tiempo de carga del modelo en milisegundos. |
| `prompt` | Prompt enviado al modelo. |
| `input_tokens` | Tokens de entrada del prompt. |
| `output_tokens` | Tokens generados por el modelo. |
| `ttft_ms` | Tiempo hasta el primer token, en milisegundos. |
| `tokens_per_second` | Throughput de generación. |
