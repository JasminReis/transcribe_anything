"""Glue between UI and core: owns the recorder and the transcription worker."""

from __future__ import annotations

import logging
import queue
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from transcribe_anywhere.audio.capture import SessionRecorder
from transcribe_anywhere.audio.devices import resolve_loopback, resolve_mic
from transcribe_anywhere.config import SAMPLE_RATE, SEGMENT_SECONDS, Settings
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.transcription.engine import Cancelled, Transcriber
from transcribe_anywhere.transcription.job import transcribe_session

log = logging.getLogger(__name__)


class TranscriptionWorker(QThread):
    """Processes sessions one after another; keeps the model loaded between jobs."""

    progress = Signal(str, int, int)        # session id, done, total
    finished_session = Signal(str, str)     # session id, final status
    status = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.busy = False
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._transcriber: Transcriber | None = None
        self._key: tuple | None = None
        self._cancel = False

    def enqueue(self, folder: Path) -> None:
        self._queue.put(folder)

    def shutdown(self) -> None:
        self._cancel = True
        self._queue.put(None)
        self.wait(5000)

    def _transcriber_for(self, session: Session) -> Transcriber:
        s = self.settings
        key = (s.model, s.compute_device, session.language, s.hotwords)
        if self._transcriber is None or key != self._key:
            self._transcriber = Transcriber(s.model, s.compute_device, session.language, s.hotwords)
            self._transcriber.load(self.status.emit)
            self._key = key
        return self._transcriber

    def run(self) -> None:
        while (folder := self._queue.get()) is not None:
            self.busy = True
            session = Session.load(folder)
            session.status, session.error = "transcribing", ""
            session.save()
            self.progress.emit(session.id, 0, 0)
            try:
                tr = self._transcriber_for(session)
                session.model = f"{tr.model_name} ({tr.device})"
                transcribe_session(
                    session,
                    tr,
                    on_progress=lambda d, t, sid=session.id: self.progress.emit(sid, d, t),
                    should_cancel=lambda: self._cancel,
                )
                session.status = "done"
            except Cancelled:
                session.status = "interrupted"
            except Exception as exc:
                log.exception("Transcription failed")
                session.status, session.error = "failed", str(exc)
            session.save()
            self.busy = not self._queue.empty()
            self.finished_session.emit(session.id, session.status)
            if self._cancel:
                return


class Controller(QObject):
    state_changed = Signal(str)            # idle | recording | transcribing
    sessions_changed = Signal()
    progress = Signal(str, int, int)
    notify = Signal(str, str)              # title, message
    status = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.recorder: SessionRecorder | None = None
        self.session: Session | None = None
        self.worker = TranscriptionWorker(settings)
        self.worker.progress.connect(self.progress)
        self.worker.progress.connect(lambda *_: self._emit_state())
        self.worker.finished_session.connect(self._on_transcribed)
        self.worker.status.connect(self.status)
        self.worker.start()

    @property
    def state(self) -> str:
        if self.recorder:
            return "recording"
        return "transcribing" if self.worker.busy else "idle"

    def _emit_state(self) -> None:
        self.state_changed.emit(self.state)

    # --- recording ---------------------------------------------------------
    def start_recording(self, title: str = "") -> bool:
        if self.recorder:
            return False
        try:
            sources = {
                "mic": resolve_mic(self.settings.mic_device),
                "system": resolve_loopback(self.settings.loopback_device),
            }
        except Exception as exc:
            self.notify.emit("Aufnahme nicht möglich", f"Audiogerät nicht gefunden: {exc}")
            return False
        self.session = Session.create(self.settings.storage_path, title, self.settings.language)
        self.recorder = SessionRecorder(self.session.audio_dir, sources, SAMPLE_RATE, SEGMENT_SECONDS)
        self.recorder.start()
        self.sessions_changed.emit()
        self._emit_state()
        return True

    def stop_recording(self) -> None:
        if not self.recorder or not self.session:
            return
        self.session.duration = round(self.recorder.stop(), 1)
        errors = self.recorder.errors()
        self.session.ended_at = datetime.now().isoformat(timespec="seconds")
        self.session.status = "recorded"
        self.session.save()
        self.recorder = None
        if errors:
            details = ", ".join(f"{k}: {v}" for k, v in errors.items())
            self.notify.emit("Problem bei der Aufnahme", details)
        self.worker.enqueue(self.session.folder)
        self.worker.busy = True
        self.session = None
        self.sessions_changed.emit()
        self._emit_state()

    def add_marker(self) -> None:
        if self.recorder and self.session:
            self.session.markers.append(round(self.recorder.elapsed, 1))
            self.session.save()

    def levels(self) -> dict[str, float]:
        return self.recorder.levels() if self.recorder else {}

    @property
    def elapsed(self) -> float:
        return self.recorder.elapsed if self.recorder else 0.0

    # --- transcription -----------------------------------------------------
    def transcribe(self, session: Session) -> None:
        session.status = "recorded"
        session.save()
        self.worker.enqueue(session.folder)
        self.worker.busy = True
        self.sessions_changed.emit()
        self._emit_state()

    def _on_transcribed(self, session_id: str, status: str) -> None:
        if status == "done":
            self.notify.emit("Transkript fertig", "Das Transkript ist bereit.")
        elif status == "failed":
            self.notify.emit("Transkription fehlgeschlagen", "Details in der Sitzung.")
        self.sessions_changed.emit()
        self._emit_state()

    def shutdown(self) -> None:
        if self.recorder:
            self.stop_recording()
        self.worker.shutdown()
