"""Desktop dashboard for the PULSO emergency-room workflow."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any

import flet as ft

from pulso.application.documentation import build_document
from pulso.application.encounter import EncounterService
from pulso.application.order_flow import OrderService
from pulso.domain.clinical_events import ORDER_TYPES, ActorRole, ClinicalEvent
from pulso.infrastructure.audio.recorder import MicrophoneRecorder
from pulso.infrastructure.database.sqlite import SQLiteDatabase
from pulso.infrastructure.qvac.documents import DocumentService
from pulso.infrastructure.qvac.retrieval import RetrievalService
from pulso.infrastructure.qvac.speech_output import SpeechOutputService
from pulso.infrastructure.qvac.translation import TranslationService
from pulso.infrastructure.repositories.encounters import EncounterRepository

INK = "#E8EDF5"
MUTED = "#91A0B5"
SURFACE = "#121A25"
SURFACE_2 = "#182332"
ACCENT = "#2DE2A6"
AMBER = "#FFB547"
RED = "#FF5A6B"


def pill(text: str, color: str = ACCENT) -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=11, color=color, weight=ft.FontWeight.W_600),
        bgcolor=f"{color}18",
        border=ft.Border.all(1, f"{color}44"),
        border_radius=18,
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
    )


def panel(content: ft.Control, *, padding: int = 20) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=SURFACE,
        border=ft.Border.all(1, "#223044"),
        border_radius=18,
        padding=padding,
    )


class PulsoApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.database = SQLiteDatabase()
        self.database.initialize()
        self.repository = EncounterRepository(self.database)
        self.encounters = EncounterService(self.repository)
        self.orders = OrderService(self.repository)
        self.recorder = MicrophoneRecorder()
        self.documents = DocumentService()
        self.retrieval = RetrievalService()
        self.translation = TranslationService()
        self.speech_output = SpeechOutputService()
        self.file_picker = ft.FilePicker()
        page.services.append(self.file_picker)
        self.encounter_id: str | None = None
        self.event_controls = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        self.order_controls = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        self.status = ft.Text("Sin atención activa", color=MUTED, size=13)
        self.capture_status = ft.Text("LISTO", color=ACCENT, size=12, weight=ft.FontWeight.BOLD)
        self.patient = ft.TextField(label="Paciente / referencia", value="DEMO-001")
        self.bed = ft.TextField(label="Cubículo", value="Trauma 2")
        self.clinician = ft.TextField(label="Profesional", value="dra.rivera")
        self.input = ft.TextField(
            hint_text="Ej.: Pulso, solicitar radiografía portátil de tórax",
            multiline=True,
            min_lines=3,
            max_lines=5,
            border_color="#33445C",
            focused_border_color=ACCENT,
        )
        self.busy = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
        self.microphone_button = ft.FilledButton(
            "Iniciar escucha",
            icon=ft.Icons.MIC,
            on_click=self.toggle_microphone,
        )
        self.rag_query = ft.TextField(
            hint_text="Verificar documentación o protocolo",
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        self.rag_results = ft.Column(spacing=8)
        self.patient_language = ft.Dropdown(
            label="Idioma del paciente",
            value="en",
            options=[
                ft.DropdownOption(key=code, text=label)
                for code, label in [
                    ("en", "English"),
                    ("pt", "Português"),
                    ("fr", "Français"),
                    ("de", "Deutsch"),
                    ("it", "Italiano"),
                    ("nl", "Nederlands"),
                    ("fi", "Suomi"),
                    ("cs", "Čeština"),
                    ("sv", "Svenska"),
                ]
            ],
        )
        self.patient_phrase = ft.TextField(hint_text="Mensaje del paciente")
        self.doctor_phrase = ft.TextField(hint_text="Respuesta breve del médico")
        self.translation_result = ft.Text("", color=INK, size=12)

    def toast(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(message, color=INK),
                bgcolor="#7A2633" if error else "#173D35",
                duration=3500,
            )
        )

    def start_encounter(self, _: ft.Event[ft.Button]) -> None:
        try:
            encounter = self.encounters.start(
                patient_ref=self.patient.value or "",
                bed=self.bed.value or "",
                clinician_id=self.clinician.value or "",
            )
            self.encounter_id = encounter.id
            self.status.value = f"{encounter.patient_ref} · {encounter.bed} · captura local"
            self.capture_status.value = "ESCUCHANDO"
            self.toast("Atención iniciada en el dispositivo")
            self.page.update()
        except Exception as error:
            self.toast(str(error), True)

    async def process_text(self, _: ft.Event[ft.Button]) -> None:
        if not self.encounter_id:
            self.toast("Inicia una atención antes de capturar", True)
            return
        if not (self.input.value or "").strip():
            self.toast("Escribe o dicta un fragmento", True)
            return
        self.busy.visible = True
        self.capture_status.value = "QVAC PROCESANDO"
        self.page.update()
        try:
            events = await asyncio.to_thread(
                self.encounters.capture_text,
                self.encounter_id,
                self.input.value or "",
                speaker=ActorRole.UNKNOWN,
            )
            self.add_events(events)
            self.input.value = ""
            self.toast(f"{len(events)} evento(s) clínico(s) extraído(s)")
        except Exception as error:
            self.toast(f"No se pudo procesar: {error}", True)
        finally:
            self.busy.visible = False
            self.capture_status.value = "ESCUCHANDO"
            self.page.update()

    def add_events(self, events: list[ClinicalEvent]) -> None:
        for event in events:
            self.event_controls.controls.insert(0, self.event_card(event))
            if event.type in ORDER_TYPES and event.actionable:
                order = self.orders.draft_from_event(
                    event, actor=self.clinician.value or "local.clinician"
                )
                self.order_controls.controls.insert(0, self.order_card(order.model_dump()))

    async def toggle_microphone(self, _: ft.Event[ft.Button]) -> None:
        if not self.encounter_id:
            self.toast("Inicia una atención antes de escuchar", True)
            return
        if not self.recorder.recording:
            try:
                self.recorder.start()
                self.microphone_button.content = "Detener y procesar"
                self.microphone_button.icon = ft.Icons.STOP_CIRCLE
                self.capture_status.value = "ESCUCHANDO AUDIO"
                self.page.update()
            except Exception as error:
                self.toast(f"Micrófono no disponible: {error}", True)
            return
        try:
            path = self.recorder.stop()
            self.busy.visible = True
            self.microphone_button.disabled = True
            self.capture_status.value = "ASR + DIARIZACIÓN + MEDPSY"
            self.page.update()
            events = await asyncio.to_thread(self.encounters.capture_audio, self.encounter_id, path)
            self.add_events(events)
            self.toast(f"Audio procesado: {len(events)} evento(s)")
        except Exception as error:
            self.toast(f"No se pudo procesar el audio: {error}", True)
        finally:
            self.busy.visible = False
            self.microphone_button.disabled = False
            self.microphone_button.content = "Iniciar escucha"
            self.microphone_button.icon = ft.Icons.MIC
            self.capture_status.value = "ESCUCHANDO"
            self.page.update()

    async def import_document(self, _: ft.Event[ft.Button]) -> None:
        if not self.encounter_id:
            self.toast("Inicia una atención antes de importar documentos", True)
            return
        files = await self.file_picker.pick_files(
            dialog_title="Documento clínico autorizado",
            allowed_extensions=["png", "jpg", "jpeg", "bmp"],
        )
        if not files or not files[0].path:
            return
        self.busy.visible = True
        self.capture_status.value = "OCR LOCAL"
        self.page.update()
        try:
            blocks = await asyncio.to_thread(self.documents.read, files[0].path)
            checksum = await asyncio.to_thread(
                lambda: hashlib.sha256(Path(files[0].path).read_bytes()).hexdigest()
            )
            self.repository.save_evidence_document(
                self.encounter_id,
                local_path=files[0].path,
                sha256=checksum,
                ocr_blocks=blocks,
                actor=self.clinician.value or "local.clinician",
            )
            text = " ".join(
                str(block.get("text", ""))
                for block in blocks
                if float(block.get("confidence", 0)) >= 0.45
            )
            self.input.value = text
            self.toast("OCR completado; revisa el texto antes de incorporarlo")
        except Exception as error:
            self.toast(f"No se pudo leer el documento: {error}", True)
        finally:
            self.busy.visible = False
            self.capture_status.value = "ESCUCHANDO"
            self.page.update()

    async def verify_rag(self, _: ft.Event[ft.Button]) -> None:
        query = (self.rag_query.value or "").strip()
        if not query:
            self.toast("Escribe qué deseas verificar", True)
            return
        self.rag_results.controls = [ft.ProgressRing(width=18, height=18)]
        self.page.update()
        try:
            results = await asyncio.to_thread(
                self.retrieval.search, query, "pulso-emergency-ops", 3
            )
            if self.encounter_id:
                self.repository.save_rag_check(
                    self.encounter_id,
                    query=query,
                    results=results,
                    actor=self.clinician.value or "local.clinician",
                )
            self.rag_results.controls = [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(
                                f"Coincidencia {float(item.get('score', 0)):.2f}",
                                color=ACCENT,
                                size=10,
                            ),
                            ft.Text(str(item.get("content", ""))[:360], color=MUTED, size=11),
                        ],
                        spacing=4,
                    ),
                    bgcolor=SURFACE_2,
                    border_radius=10,
                    padding=10,
                )
                for item in results
            ] or [ft.Text("Sin coincidencias; requiere revisión manual", color=AMBER, size=11)]
        except Exception as error:
            self.rag_results.controls = [ft.Text(str(error), color=RED, size=11)]
        self.page.update()

    async def translate_patient(self, _: ft.Event[ft.Button]) -> None:
        text = (self.patient_phrase.value or "").strip()
        if not text:
            return
        self.translation_result.value = "Traduciendo localmente…"
        self.page.update()
        try:
            translated = await asyncio.to_thread(
                self.translation.translate,
                text,
                self.patient_language.value or "en",
                "es",
            )
            self.translation_result.value = f"Paciente → médico: {translated}"
        except Exception as error:
            self.translation_result.value = f"Traducción no disponible: {error}"
            self.translation_result.color = RED
        self.page.update()

    async def speak_to_patient(self, _: ft.Event[ft.Button]) -> None:
        text = (self.doctor_phrase.value or "").strip()
        if not text:
            return
        self.translation_result.value = "Traduciendo y generando voz local…"
        self.page.update()
        try:
            language = self.patient_language.value or "en"
            translated = await asyncio.to_thread(self.translation.translate, text, "es", language)
            destination = self.database.path.parent / "patient-response.wav"
            await asyncio.to_thread(
                self.speech_output.synthesize, translated, destination, language
            )
            self.translation_result.value = f"Médico → paciente: {translated}"
            if sys.platform == "win32":
                import winsound

                await asyncio.to_thread(winsound.PlaySound, str(destination), winsound.SND_FILENAME)
        except Exception as error:
            self.translation_result.value = f"Respuesta no disponible: {error}"
            self.translation_result.color = RED
        self.page.update()

    def event_card(self, event: ClinicalEvent) -> ft.Container:
        color = AMBER if event.confirmation_required else ACCENT
        detail = ", ".join(f"{key}: {value}" for key, value in event.payload.items())
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=4, height=54, bgcolor=color, border_radius=4),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    pill(event.type.value.replace("_", " "), color),
                                    pill(event.state.value, color),
                                ]
                            ),
                            ft.Text(detail or "Evidencia registrada", color=INK, size=13),
                            ft.Text(
                                f"Fuente: {', '.join(event.evidence_utterance_ids)}",
                                color=MUTED,
                                size=10,
                            ),
                        ],
                        spacing=5,
                        expand=True,
                    ),
                ]
            ),
            bgcolor=SURFACE_2,
            border_radius=12,
            padding=12,
        )

    def order_card(self, order: dict[str, Any]) -> ft.Container:
        status = ft.Text(order["state"].upper(), color=AMBER, size=10, weight=ft.FontWeight.BOLD)

        def confirm(_: ft.Event[ft.Button]) -> None:
            try:
                confirmed = self.orders.confirm(
                    order["id"],
                    clinician_id=self.clinician.value or "local.clinician",
                    signature=f"local:{self.clinician.value or 'clinician'}",
                )
                dispatched = self.orders.dispatch(confirmed.id)
                status.value = dispatched.state.value.upper()
                status.color = ACCENT
                self.toast(f"Orden enviada a {dispatched.destination}")
                self.page.update()
            except Exception as error:
                self.toast(str(error), True)

        def cancel(_: ft.Event[ft.Button]) -> None:
            try:
                cancelled = self.orders.cancel(
                    order["id"],
                    actor=self.clinician.value or "local.clinician",
                    reason="cancelada por el profesional",
                )
                status.value = cancelled.state.value.upper()
                status.color = RED
                self.toast("Orden cancelada; permanece en la trazabilidad")
                self.page.update()
            except Exception as error:
                self.toast(str(error), True)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(order["destination"], color=INK, weight=ft.FontWeight.BOLD),
                            status,
                        ]
                    ),
                    ft.Text(order["request"], color=MUTED, size=12),
                    ft.Row(
                        [
                            ft.TextButton(
                                "Confirmar y enviar",
                                icon=ft.Icons.CHECK_CIRCLE,
                                on_click=confirm,
                            ),
                            ft.TextButton("Cancelar", icon=ft.Icons.CANCEL, on_click=cancel),
                        ]
                    ),
                ],
                spacing=6,
            ),
            bgcolor=SURFACE_2,
            border=ft.Border.all(1, "#314158"),
            border_radius=12,
            padding=12,
        )

    def critical(self, _: ft.Event[ft.Button]) -> None:
        if not self.encounter_id:
            self.toast("No hay una atención activa", True)
            return
        self.encounters.critical_mode(self.encounter_id, actor=self.clinician.value or "clinician")
        self.capture_status.value = "MODO CRÍTICO · SIN INTERRUPCIONES"
        self.capture_status.color = RED
        self.toast("Modo crítico activado: captura silenciosa y revisión diferida")
        self.page.update()

    def review(self, _: ft.Event[ft.Button]) -> None:
        if not self.encounter_id:
            self.toast("No hay una atención activa", True)
            return
        events = self.repository.list_events(self.encounter_id)
        document = build_document(self.encounter_id, events)
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Revisión clínica", color=INK),
                content=ft.Container(
                    ft.Column(
                        [
                            ft.Text(document.summary, color=INK),
                            ft.Text(
                                "La documentación permanece sin firmar hasta la aprobación médica.",
                                color=AMBER,
                                size=12,
                            ),
                        ],
                        tight=True,
                    ),
                    width=560,
                ),
                actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
                bgcolor=SURFACE,
            )
        )

    def build(self) -> ft.Control:
        header = ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            ft.Icon(ft.Icons.ECG_HEART, color="#07130F", size=24),
                            bgcolor=ACCENT,
                            border_radius=12,
                            padding=10,
                        ),
                        ft.Column(
                            [
                                ft.Text("PULSO", color=INK, size=24, weight=ft.FontWeight.BOLD),
                                ft.Text("Clinical operations · on device", color=MUTED, size=11),
                            ],
                            spacing=0,
                        ),
                    ]
                ),
                ft.Row([pill("QVAC LOCAL"), pill("SIN NUBE", "#7FB7FF")]),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        identity = panel(
            ft.Column(
                [
                    ft.Text("ATENCIÓN ACTIVA", color=MUTED, size=11, weight=ft.FontWeight.BOLD),
                    ft.Row([self.patient, self.bed, self.clinician]),
                    ft.Row(
                        [
                            ft.Button(
                                "Iniciar atención",
                                icon=ft.Icons.PLAY_ARROW,
                                on_click=self.start_encounter,
                            ),
                            ft.OutlinedButton(
                                "Código / crítico", icon=ft.Icons.EMERGENCY, on_click=self.critical
                            ),
                            ft.OutlinedButton(
                                "Revisar nota", icon=ft.Icons.FACT_CHECK, on_click=self.review
                            ),
                            self.status,
                        ]
                    ),
                ],
                spacing=12,
            )
        )
        capture = panel(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Captura ambiental", color=INK, size=18, weight=ft.FontWeight.BOLD
                            ),
                            ft.Row([self.busy, self.capture_status]),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        "Los hechos relevantes se extraen localmente. "
                        "Solo ‘Pulso, ...’ abre una orden.",
                        color=MUTED,
                        size=12,
                    ),
                    self.input,
                    ft.Row(
                        [
                            self.microphone_button,
                            ft.OutlinedButton(
                                "Documento",
                                icon=ft.Icons.DOCUMENT_SCANNER,
                                on_click=self.import_document,
                            ),
                            ft.FilledButton(
                                "Procesar con QVAC",
                                icon=ft.Icons.AUTO_AWESOME,
                                on_click=self.process_text,
                            ),
                        ]
                    ),
                ],
                spacing=12,
            )
        )
        timeline = panel(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Línea clínica", color=INK, size=18, weight=ft.FontWeight.BOLD),
                            pill("EVIDENCIA TRAZABLE", "#7FB7FF"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.event_controls,
                ],
                expand=True,
            )
        )
        orders = panel(
            ft.Column(
                [
                    ft.Text("Órdenes", color=INK, size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("Lectura de vuelta · firma · estado", color=MUTED, size=11),
                    self.order_controls,
                    ft.Container(
                        ft.Column(
                            [
                                ft.Icon(ft.Icons.SHIELD_OUTLINED, color=ACCENT),
                                ft.Text("Control humano", color=INK, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "PULSO documenta y coordina. El profesional decide y firma.",
                                    color=MUTED,
                                    size=11,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor="#102820",
                        border_radius=12,
                        padding=16,
                    ),
                ],
                expand=True,
            )
        )
        knowledge = panel(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Evidencia local", color=INK, size=17, weight=ft.FontWeight.BOLD
                            ),
                            pill("RAG QVAC", "#7FB7FF"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        "Recupera fragmentos con fuente. No diagnostica ni autoriza órdenes.",
                        color=MUTED,
                        size=11,
                    ),
                    self.rag_query,
                    ft.OutlinedButton(
                        "Buscar evidencia",
                        icon=ft.Icons.SEARCH,
                        on_click=self.verify_rag,
                    ),
                    self.rag_results,
                ],
                spacing=10,
            )
        )
        interpreter = panel(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Intérprete", color=INK, size=17, weight=ft.FontWeight.BOLD),
                            pill("TRANSLATEPSY", "#C79BFF"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.patient_language,
                    self.patient_phrase,
                    ft.TextButton(
                        "Traducir al médico",
                        icon=ft.Icons.TRANSLATE,
                        on_click=self.translate_patient,
                    ),
                    self.doctor_phrase,
                    ft.TextButton(
                        "Traducir y hablar",
                        icon=ft.Icons.RECORD_VOICE_OVER,
                        on_click=self.speak_to_patient,
                    ),
                    self.translation_result,
                ],
                spacing=8,
            )
        )
        return ft.Column(
            [
                header,
                identity,
                ft.Row(
                    [
                        ft.Column([capture, timeline], expand=7),
                        ft.Column(
                            [orders, knowledge, interpreter],
                            expand=3,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ],
                    expand=True,
                    spacing=16,
                ),
            ],
            expand=True,
            spacing=16,
        )


def main(page: ft.Page) -> None:
    page.title = "PULSO"
    page.bgcolor = "#0A1018"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 24
    page.window.width = 1440
    page.window.height = 900
    page.window.min_width = 1050
    page.window.min_height = 720
    page.add(PulsoApp(page).build())


def run_app() -> None:
    ft.run(main)


if __name__ == "__main__":
    run_app()
