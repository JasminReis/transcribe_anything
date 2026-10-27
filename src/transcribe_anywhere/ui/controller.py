"""Glue between UI and core: owns the recorder and the transcription worker."""

from __future__ import annotations

import dataclasses
import logging
import queue
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from transcribe_anywhere.audio.capture import SessionRecorder
from transcribe_anywhere.audio.devices import resolve_loopback, resolve_mic
from transcribe_anywhere.config import SAMPLE_RATE, SEGMENT_SECONDS, Settings
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.transcription.engine import Cancelled, create_transcriber, resolve_engine
from transcribe_anywhere.transcription.job import Progress, transcribe_session
from transcribe_anywhere.transcription.live import LiveTranscriber

log = logging.getLogger(__name__)


class LiveControl:
    """Handle for a running live transcription; stop() is called when the recording ends."""

    def __init__(self):
        self.recording = True

    def stop(self) -> None:
        self.recording = False


class TranscriptionWorker(QThread):
    """One thread for all speech recognition: live jobs and full (re-)transcriptions.

    Jobs run one after another and share the loaded model.
    """

    progress = Signal(str, object)          # session id, job.Progress
    finished_session = Signal(str, str)     # session id, final status
    status = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.busy = False
        self._queue: queue.Queue = queue.Queue()
        self._transcriber = None
        self._key: tuple | None = None
        self._cancel = False

    def enqueue(self, folder: Path, engine: str | None = None) -> None:
        self._queue.put(("full", folder, engine, None))

    def start_live(self, folder: Path) -> LiveControl:
        control = LiveControl()
        self._queue.put(("live", folder, None, control))
        return control

    def shutdown(self) -> None:
        self._cancel = True
        self._queue.put(None)
        self.wait(5000)

    def _transcriber_for(self, session: Session, engine: str | None = None):
        s = self.settings
        kind = resolve_engine(engine or s.engine, s.compute_device)
        key = (kind, s.model, s.compute_device, session.language, s.hotwords)
        if self._transcriber is None or key != self._key:
            self._transcriber = create_transcriber(kind, s.model, s.compute_device, session.language, s.hotwords)
            self._key = key          # the model itself is loaded lazily
        return self._transcriber

    def _reporter(self, session_id: str):
        last = {"t": 0.0, "stage": ""}

        def report(p):
            # throttle to ~10 updates/s, but never drop a stage change
            now = time.monotonic()
            if p.stage != last["stage"] or now - last["t"] > 0.1 or p.stage == "done":
                last.update(t=now, stage=p.stage)
                self.progress.emit(session_id, dataclasses.replace(p))
        return report

    def run(self) -> None:
        while (item := self._queue.get()) is not None:
            kind, folder, engine, control = item
            self.busy = True
            if kind == "live":
                session_id, status = self._run_live(folder, control)
            else:
                session_id, status = self._run_full(folder, engine)
            self.busy = not self._queue.empty()
            self.finished_session.emit(session_id, status)
            if self._cancel:
                return

    def _run_full(self, folder: Path, engine: str | None) -> tuple[str, str]:
        session = Session.load(folder)
        session.status, session.error = "transcribing", ""
        session.save()
        report = self._reporter(session.id)
        try:
            tr = self._transcriber_for(session, engine)
            transcribe_session(session, tr, report, should_cancel=lambda: self._cancel)
            session.model = tr.label
            session.status = "done"
        except Cancelled:
            session.status = "interrupted"
        except Exception as exc:
            log.exception("Transcription failed")
            session.status, session.error = "failed", str(exc)
        session.save()
        return session.id, session.status

    def _run_live(self, folder: Path, control: LiveControl) -> tuple[str, str]:
        session = Session.load(folder)
        report = self._reporter(session.id)
        try:
            tr = self._transcriber_for(session)
            if not tr.loaded:
                report(Progress("load", engine=tr.label))
                tr.load(self.status.emit)
            live = LiveTranscriber(session, tr)
            live.run(lambda: control.recording, report, should_cancel=lambda: self._cancel)
            final = Session.load(folder)            # fresh copy: duration, markers from the recorder
            final.speech_seconds = round(live.speech_seconds, 1)
            final.model = f"{tr.label} · live"
            final.status = "done"
        except Cancelled:
            final = Session.load(folder)
            final.status = "interrupted"
        except Exception:
            log.exception("Live transcription failed – will transcribe after the recording")
            self.status.emit("Live-Transkription unterbrochen – wird nach der Aufnahme nachgeholt")
            while control.recording and not self._cancel:
                time.sleep(0.5)
            if self._cancel:
                final = Session.load(folder)
                final.status = "interrupted"
            else:
                return self._run_full(folder, None)
        final.save()
        return final.id, final.status


class Controller(QObject):
    state_changed = Signal(str)            # idle | recording | transcribing
    sessions_changed = Signal()
    progress = Signal(str, object)
    notify = Signal(str, str)              # title, message
    status = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.recorder: SessionRecorder | None = None
        self.session: Session | None = None
        self._live: LiveControl | None = None
        self.live_progress: Progress | None = None
        self.worker = TranscriptionWorker(settings)
        self.worker.progress.connect(self._remember_live_progress)
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
        self.live_progress = None
        if self.settings.live:
            self._live = self.worker.start_live(self.session.folder)
            self.worker.busy = True
        self.sessions_changed.emit()
        self._emit_state()
        return True

    def stop_recording(self) -> None:
        if not self.recorder or not self.session:
            return
        self.session.duration = round(self.recorder.stop(), 1)
        errors = self.recorder.errors()
        self.session.ended_at = datetime.now().isoformat(timespec="seconds")
        self.recorder = None
        if errors:
            details = ", ".join(f"{k}: {v}" for k, v in errors.items())
            self.notify.emit("Problem bei der Aufnahme", details)
        if self._live:
            self.session.status = "transcribing"     # live job now transcribes the rest
            self.session.save()
            self._live.stop()
            self._live = None
        else:
            self.session.status = "recorded"
            self.session.save()
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
    def _remember_live_progress(self, session_id: str, p) -> None:
        if self.session and session_id == self.session.id:
            self.live_progress = p

    def live_status(self) -> tuple[str, str] | None:
        """Short status for the recording pill: (text, colour)."""
        if not self.recorder or not self.settings.live:
            return None
        p = self.live_progress
        if p is None or p.stage == "load":
            return "Live startet …", "#94a3b8"
        if p.lag < 45:
            return "Live ✓", "#22c55e"
        minutes, seconds = divmod(int(p.lag), 60)
        return f"Live ⟳ {minutes}:{seconds:02d}", "#f5a524"

    def transcribe(self, session: Session, engine: str | None = None) -> None:
        session.status = "recorded"
        session.save()
        self.worker.enqueue(session.folder, engine)
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
