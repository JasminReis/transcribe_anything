"""'KI-Auswertung' tab: hardware check, Ollama model, summary and correction."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.config import Settings
from transcribe_anywhere.llm import hardware, tasks
from transcribe_anywhere.llm.ollama import Cancelled, Ollama, find_installed
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.transcript import read_segments, write_segments

LEVEL_COLORS = {"good": "#16a34a", "ok": "#2563eb", "slow": "#d97706", "no": "#dc2626"}
# Rough CPU-only throughput on the target laptop class (characters of transcript per second).
CPU_SUMMARY_CPS = 20
CPU_CORRECT_CPS = 8

_hw_cache: tuple[hardware.Hardware, hardware.Advice] | None = None


def hardware_advice() -> tuple[hardware.Hardware, hardware.Advice]:
    global _hw_cache
    if _hw_cache is None:
        hw = hardware.detect()
        _hw_cache = (hw, hardware.advise(hw))
    return _hw_cache


class LlmJob(QThread):
    token = Signal(str)
    status = Signal(str, int, int)
    done = Signal(bool, object, str)       # ok, result, error text

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelled = False

    def run(self) -> None:
        try:
            self.done.emit(True, self.fn(self), "")
        except Cancelled:
            self.done.emit(False, None, "Abgebrochen.")
        except Exception as exc:
            self.done.emit(False, None, str(exc))


class AiPanel(QWidget):
    corrected = Signal(str)                # session id

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.session: Session | None = None
        self.job: LlmJob | None = None
        self._buffer = ""
        hw, self.advice = hardware_advice()

        # --- hardware card
        badge = QLabel(self.advice.headline)
        badge.setStyleSheet(f"background:{LEVEL_COLORS[self.advice.level]}; color:white; border-radius:9px;"
                            " padding:2px 10px; font-weight:600;")
        hw_text = QLabel(f"<b>Deine Hardware</b><br>{hw.cpu} · {hw.ram_gb:.0f} GB RAM"
                         + (f" · {hw.gpu}" if hw.gpu else "") + f"<br><span style='color:#64748b'>"
                         f"{self.advice.detail}</span>")
        hw_text.setWordWrap(True)
        hw_row = QHBoxLayout()
        hw_row.addWidget(hw_text, 1)
        hw_row.addWidget(badge, 0, Qt.AlignTop)

        # --- Ollama row
        self.ollama_status = QLabel()
        self.ollama_status.setOpenExternalLinks(True)
        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(260)
        self.model_box.currentIndexChanged.connect(self._model_chosen)
        self.pull_btn = QPushButton("Empfohlenes Modell laden", clicked=self._pull)
        refresh = QPushButton("↻", clicked=self.refresh, toolTip="Neu prüfen")
        refresh.setFixedWidth(34)
        model_row = QHBoxLayout()
        model_row.addWidget(self.ollama_status)
        model_row.addStretch(1)
        model_row.addWidget(self.model_box)
        model_row.addWidget(self.pull_btn)
        model_row.addWidget(refresh)

        # --- actions
        self.summary_btn = QPushButton("✨  Zusammenfassen", objectName="primary", clicked=self._summarize)
        self.correct_btn = QPushButton("✎  Transkript korrigieren", clicked=self._correct)
        self.cancel_btn = QPushButton("Abbrechen", clicked=self._cancel)
        self.cancel_btn.hide()
        self.copy_btn = QPushButton("⧉  Kopieren", clicked=self._copy)
        self.estimate = QLabel()
        self.estimate.setStyleSheet("color:#64748b;")
        actions = QHBoxLayout()
        for w in (self.summary_btn, self.correct_btn, self.cancel_btn):
            actions.addWidget(w)
        actions.addWidget(self.estimate, 1)
        actions.addWidget(self.copy_btn)

        self.status = QLabel()
        self.status.setStyleSheet("color:#64748b;")
        self.bar = QProgressBar(objectName="thin", textVisible=False)
        self.bar.hide()

        self.output = QTextBrowser(openExternalLinks=True)
        self.output.setStyleSheet("QTextBrowser { font-size: 14px; padding: 10px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addLayout(hw_row)
        layout.addLayout(model_row)
        layout.addSpacing(4)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(self.output, 1)

        self._render_timer = QTimer(self, interval=120, timeout=self._render_stream)
        self.refresh()

    # --- state -------------------------------------------------------------------
    def client(self) -> Ollama:
        return Ollama(self.settings.ollama_url)

    def refresh(self) -> None:
        client = self.client()
        version = client.version()
        self.model_box.blockSignals(True)
        self.model_box.clear()
        self.pull_btn.hide()
        if version is None:
            self.ollama_status.setText(
                "<span style='color:#dc2626'>●</span> Ollama nicht gefunden – "
                "<a href='https://ollama.com/download'>ollama.com/download</a> installieren und starten")
            self.model_box.setEnabled(False)
        else:
            names = [m["name"] for m in client.models() if "embed" not in m["name"] and "bge" not in m["name"]]
            recommended = find_installed(self.advice.model, names)
            if recommended:
                self.model_box.addItem(f"★ {recommended} (empfohlen)", recommended)
            for n in sorted(names):
                if n != recommended:
                    self.model_box.addItem(n, n)
            if self.advice.model and not recommended:
                self.pull_btn.setText(f"Empfohlenes Modell laden ({self.advice.model})")
                self.pull_btn.show()
            chosen = self.settings.llm_model or recommended or ""
            idx = self.model_box.findData(chosen)
            self.model_box.setCurrentIndex(max(idx, 0))
            self.model_box.setEnabled(bool(names))
            self.ollama_status.setText(f"<span style='color:#16a34a'>●</span> Ollama {version} · "
                                       f"{len(names)} Modelle")
        self.model_box.blockSignals(False)
        self._update_enabled()

    def _model_chosen(self) -> None:
        self.settings.llm_model = self.model_box.currentData() or ""
        self.settings.save()

    def set_session(self, session: Session | None) -> None:
        if self.session and session and session.id == self.session.id:
            self.session = session          # same meeting: keep output and status, refresh state only
            self._update_enabled()
            return
        if self.job:                        # a task is running for another meeting – leave it alone
            return
        self.session = session
        self.output.clear()
        if session and session.summary_path.exists():
            self.output.setMarkdown(session.summary_path.read_text("utf-8"))
            self.status.setText("Gespeicherte Zusammenfassung")
        else:
            self.status.setText("")
        self._update_enabled()

    def _segments(self):
        if not self.session:
            return []
        path = self.session.corrected_path if self.session.corrected_path.exists() else self.session.transcript_path
        return read_segments(path)

    def _update_enabled(self) -> None:
        running = self.job is not None
        ready = (self.session is not None and self.session.status == "done"
                 and self.model_box.count() > 0 and self.model_box.isEnabled())
        self.summary_btn.setEnabled(ready and not running)
        self.correct_btn.setEnabled(ready and not running)
        self.cancel_btn.setVisible(running)
        self.copy_btn.setEnabled(bool(self.output.toPlainText().strip()))
        chars = sum(len(s.text) for s in self._segments()) if ready else 0
        if ready and self.advice.level in ("slow", "no") and chars:
            self.estimate.setText(f"grobe Schätzung auf diesem Gerät: Zusammenfassung ~{_mins(chars / CPU_SUMMARY_CPS)},"
                                  f" Korrektur ~{_mins(chars / CPU_CORRECT_CPS)}")
        elif self.session and self.session.status != "done":
            self.estimate.setText("Verfügbar, sobald das Transkript fertig ist.")
        else:
            self.estimate.clear()

    # --- jobs -----------------------------------------------------------------------
    def _start(self, fn, on_done) -> None:
        self.job = LlmJob(fn)
        self.job.token.connect(self._on_token)
        self.job.status.connect(self._on_status)
        self.job.done.connect(lambda ok, res, err: self._finish(ok, res, err, on_done))
        self.bar.setRange(0, 0)
        self.bar.show()
        self.job.start()
        self._update_enabled()

    def _summarize(self) -> None:
        session, model = self.session, self.model_box.currentData()
        segments = self._segments()
        self._buffer = ""
        self.output.clear()
        num_ctx = self.advice.num_ctx

        def run(job):
            return tasks.summarize(self.client(), model, segments, session.title, session.language, num_ctx,
                                   on_token=job.token.emit, on_status=job.status.emit,
                                   should_cancel=lambda: job.cancelled)

        def done(text):
            session.summary_path.write_text(text, "utf-8")
            self.output.setMarkdown(text)
            self.status.setText(f"Zusammenfassung gespeichert · Modell {model}")

        self._render_timer.start()
        self._start(run, done)

    def _correct(self) -> None:
        if not self.advice.correction_ok:
            answer = QMessageBox.question(
                self, "Transkript korrigieren",
                "Auf dieser Hardware dauert die Korrektur sehr lange (siehe Schätzung). Trotzdem starten?")
            if answer != QMessageBox.Yes:
                return
        session, model = self.session, self.model_box.currentData()
        segments = read_segments(session.transcript_path)       # always correct the original
        num_ctx, glossary = self.advice.num_ctx, self.settings.hotwords

        def run(job):
            return tasks.correct(self.client(), model, segments, glossary, num_ctx,
                                 on_status=job.status.emit,
                                 on_batch=lambda segs: write_segments(session.corrected_path, segs),
                                 should_cancel=lambda: job.cancelled)

        def done(fixed):
            write_segments(session.corrected_path, fixed)
            changed = sum(a.text != b.text for a, b in zip(segments, fixed))
            self.status.setText(f"Korrektur fertig: {changed} von {len(fixed)} Zeilen verbessert · "
                                "im Tab „Transkript“ zwischen Original und KI-korrigiert umschalten")
            self.corrected.emit(session.id)

        self._start(run, done)

    def _cancel(self) -> None:
        if self.job:
            self.job.cancelled = True
            self.status.setText("Wird abgebrochen …")

    def _pull(self) -> None:
        model = self.advice.model

        def run(job):
            self.client().pull(model, lambda frac, st: job.status.emit(
                f"{model} wird geladen: {st}", int(max(frac, 0) * 1000), 1000 if frac >= 0 else 0),
                should_cancel=lambda: job.cancelled)

        def done(_):
            self.settings.llm_model = model
            self.settings.save()
            self.refresh()

        self._start(run, done)

    # --- callbacks ------------------------------------------------------------------
    def _on_token(self, token: str) -> None:
        self._buffer += token

    def _render_stream(self) -> None:
        if self._buffer:
            self.output.setMarkdown(self._buffer + " ▍")
            bar = self.output.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _on_status(self, text: str, done: int, total: int) -> None:
        self.status.setText(text + " …")
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)

    def _finish(self, ok: bool, result, error: str, on_done) -> None:
        self._render_timer.stop()
        self.bar.hide()
        self.job = None
        if ok:
            on_done(result)
        else:
            self.status.setText(f"<span style='color:#dc2626'>{error}</span>")
            if self._buffer:
                self.output.setMarkdown(self._buffer)
        self._update_enabled()

    def _copy(self) -> None:
        text = self.session.summary_path.read_text("utf-8") if (
            self.session and self.session.summary_path.exists()) else self.output.toPlainText()
        QApplication.clipboard().setText(text)
        win = self.window()
        if hasattr(win, "toast"):
            win.toast("Zusammenfassung kopiert ✓")


def _mins(seconds: float) -> str:
    return f"{max(1, round(seconds / 60))} min"
