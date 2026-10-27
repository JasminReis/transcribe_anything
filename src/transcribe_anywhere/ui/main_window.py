"""Main window: record button, session library, transcript + AI tabs."""

from __future__ import annotations

import html
import time

from PySide6.QtCore import QPropertyAnimation, QSequentialAnimationGroup, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.session.export import EXPORTERS, fmt_date, fmt_duration, fmt_time
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.store import list_sessions
from transcribe_anywhere.session.transcript import Segment, read_segments
from transcribe_anywhere.ui.ai_panel import AiPanel
from transcribe_anywhere.ui.progress_card import ProgressCard
from transcribe_anywhere.ui.theme import SPEAKER_COLORS, STYLE

STATUS_ICONS = {
    "recording": "🔴", "recorded": "⏳", "transcribing": "⏳",
    "done": "✓", "interrupted": "⚠", "failed": "✗",
}


# --------------------------------------------------------------------------- copy formats
def copy_with_times(segments: list[Segment]) -> str:
    return "\n".join(f"[{fmt_time(s.start)}] {s.speaker}: {s.text}" for s in segments) + "\n"


def copy_plain(segments: list[Segment]) -> str:
    """Speaker turns as paragraphs – best for pasting into mails, docs or chat tools."""
    turns: list[tuple[str, list[str]]] = []
    for s in segments:
        if turns and turns[-1][0] == s.speaker:
            turns[-1][1].append(s.text)
        else:
            turns.append((s.speaker, [s.text]))
    return "\n\n".join(f"{who}: {' '.join(texts)}" for who, texts in turns) + "\n"


class Toast(QLabel):
    """Small message that fades in at the bottom of the window and disappears."""

    def __init__(self, parent):
        super().__init__(parent, objectName="toast")
        self.setAlignment(Qt.AlignCenter)
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0)
        fade_in = QPropertyAnimation(self._fx, b"opacity", self, duration=180, startValue=0.0, endValue=1.0)
        hold = QPropertyAnimation(self._fx, b"opacity", self, duration=1400, startValue=1.0, endValue=1.0)
        fade_out = QPropertyAnimation(self._fx, b"opacity", self, duration=400, startValue=1.0, endValue=0.0)
        self._seq = QSequentialAnimationGroup(self)
        for a in (fade_in, hold, fade_out):
            self._seq.addAnimation(a)
        self._seq.finished.connect(self.hide)
        self.hide()

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 36)
        self.show()
        self.raise_()
        self._seq.stop()
        self._seq.start()


class MainWindow(QMainWindow):
    record_toggled = Signal()
    settings_requested = Signal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Transcribe Anywhere")
        self.resize(1180, 760)
        self.setStyleSheet(STYLE)
        self._sessions: dict[str, Session] = {}
        self._last_render = 0.0
        self.hide_to_tray = True

        # --- top bar
        self.record_button = QPushButton("●  Aufnahme starten", objectName="recordButton")
        self.record_button.setCursor(Qt.PointingHandCursor)
        self.record_button.clicked.connect(self.record_toggled)
        self.title_edit = QLineEdit(placeholderText="Meeting-Titel (optional)")
        self.title_edit.setMinimumWidth(280)
        self.status_label = QLabel("Bereit")
        self.status_label.setStyleSheet("color: #64748b;")
        settings_btn = QPushButton("⚙  Einstellungen", clicked=self.settings_requested)
        top = QHBoxLayout()
        top.addWidget(self.record_button)
        top.addWidget(self.title_edit)
        top.addWidget(self.status_label, 1)
        top.addWidget(settings_btn)

        # --- left: session library
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("Sitzungen")
        heading.setStyleSheet("font-weight: 600; font-size: 13px; padding: 4px 2px;")
        lv.addWidget(heading)
        lv.addWidget(self.list)

        # --- right: header
        self.session_title = QLabel()
        self.session_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.session_meta = QLabel()
        self.session_meta.setStyleSheet("color: #64748b;")

        # --- tab 1: transcript
        self.copy_btn = QToolButton(text="⧉  Transkript kopieren", objectName="primary",
                                    popupMode=QToolButton.MenuButtonPopup)
        self.copy_btn.clicked.connect(lambda: self._copy("times"))
        copy_menu = QMenu(self.copy_btn)
        copy_menu.addAction("Mit Zeitstempeln und Sprechern", lambda: self._copy("times"))
        copy_menu.addAction("Nur Text (nach Sprechern)", lambda: self._copy("plain"))
        copy_menu.addAction("Als Markdown", lambda: self._copy("md"))
        self.copy_btn.setMenu(copy_menu)

        self.export_btn = QToolButton(text="Export ▾", popupMode=QToolButton.InstantPopup)
        menu = QMenu(self.export_btn)
        for ext, label in (("txt", "Text (.txt)"), ("md", "Markdown (.md)"), ("srt", "Untertitel (.srt)")):
            menu.addAction(label, lambda e=ext: self._export(e))
        self.export_btn.setMenu(menu)
        self.folder_btn = QPushButton("Ordner öffnen", clicked=self._open_folder)
        self.retranscribe_btn = QPushButton("Neu transkribieren", clicked=self._retranscribe)
        self.version_box = QComboBox()
        self.version_box.addItem("Original", "original")
        self.version_box.addItem("✨ KI-korrigiert", "corrected")
        self.version_box.setMinimumWidth(150)
        self.version_box.currentIndexChanged.connect(lambda *_: self._render_current())
        actions = QHBoxLayout()
        for w in (self.copy_btn, self.export_btn, self.folder_btn, self.retranscribe_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(self.version_box)

        self.progress_card = ProgressCard()
        self.progress_card.hide()
        self.view = QTextBrowser(openExternalLinks=False)
        self.view.setStyleSheet("QTextBrowser { font-size: 14px; padding: 8px; }")

        transcript_tab = QWidget()
        tv = QVBoxLayout(transcript_tab)
        tv.setContentsMargins(0, 8, 0, 0)
        tv.addLayout(actions)
        tv.addWidget(self.progress_card)
        tv.addWidget(self.view, 1)

        # --- tab 2: AI
        self.ai = AiPanel(controller.settings)
        self.ai.corrected.connect(self._on_corrected)

        self.tabs = QTabWidget(documentMode=True)
        self.tabs.addTab(transcript_tab, "Transkript")
        self.tabs.addTab(self.ai, "✨ KI-Auswertung")

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 0, 0, 0)
        rv.addWidget(self.session_title)
        rv.addWidget(self.session_meta)
        rv.addWidget(self.tabs, 1)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 880])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self._toast = Toast(root)

        controller.sessions_changed.connect(self.refresh_sessions)
        controller.state_changed.connect(self.set_state)
        controller.progress.connect(self._on_progress)
        controller.status.connect(self.status_label.setText)
        self.refresh_sessions()
        self.set_state(controller.state)

    def toast(self, text: str) -> None:
        self._toast.show_message(text)

    # --- state ---------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        recording = state == "recording"
        self.record_button.setText("■  Aufnahme beenden" if recording else "●  Aufnahme starten")
        self.record_button.setProperty("recording", recording)
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        self.title_edit.setEnabled(not recording)
        if recording:
            self.status_label.setText("Aufnahme läuft …")
        elif state == "idle":
            self.status_label.setText("Bereit")

    # --- library ---------------------------------------------------------------------
    def refresh_sessions(self) -> None:
        current = self._current_id()
        self.list.blockSignals(True)
        self.list.clear()
        self._sessions = {}
        for s in list_sessions(self.controller.settings.storage_path):
            self._sessions[s.id] = s
            dur = fmt_duration(s.duration) if s.duration else "–"
            item = QListWidgetItem(f"{s.title}\n{fmt_date(s.started_at)} · {dur} · "
                                   f"{STATUS_ICONS.get(s.status, '')} {s.status_label}")
            item.setData(Qt.UserRole, s.id)
            self.list.addItem(item)
            if s.id == current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_selected()

    def _current_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _current(self) -> Session | None:
        s = self._sessions.get(self._current_id() or "")
        return Session.load(s.folder) if s else None

    def _meta(self, s: Session) -> str:
        meta = f"{fmt_date(s.started_at)} · {fmt_duration(s.duration)} · {s.status_label}"
        if s.speech_seconds and s.duration:
            meta += f" · {fmt_duration(s.speech_seconds)} Sprache"
        if s.model:
            meta += f" · {s.model}"
        return meta

    def _show_selected(self) -> None:
        s = self._current()
        for w in (self.copy_btn, self.export_btn, self.folder_btn, self.retranscribe_btn):
            w.setEnabled(s is not None)
        self.ai.set_session(s)
        if not s:
            self.session_title.setText("Noch keine Sitzungen")
            self.session_meta.setText("Starte eine Aufnahme – das Transkript erscheint hier.")
            self.view.clear()
            self.progress_card.hide()
            self.version_box.hide()
            return
        self.session_title.setText(s.title)
        self.session_meta.setText(self._meta(s))
        busy = s.status in ("recording", "recorded", "transcribing")
        self.retranscribe_btn.setEnabled(not busy)
        self.copy_btn.setEnabled(s.transcript_path.exists())
        has_corrected = s.corrected_path.exists()
        self.version_box.setVisible(has_corrected)
        if not has_corrected:
            self.version_box.setCurrentIndex(0)
        if s.status in ("recorded", "transcribing"):
            if s.status == "recorded":
                self.progress_card.set_queued()
            self.progress_card.show()
        else:
            self.progress_card.hide()
        self._render(s)

    def _segments_for(self, s: Session) -> list[Segment]:
        if self.version_box.currentData() == "corrected" and s.corrected_path.exists():
            return read_segments(s.corrected_path)
        return read_segments(s.transcript_path)

    def _render_current(self) -> None:
        s = self._current()
        if s:
            self._render(s)

    def _render(self, s: Session) -> None:
        segments = self._segments_for(s)
        if not segments:
            hint = {
                "recording": "Aufnahme läuft. Das Transkript erscheint nach dem Beenden.",
                "recorded": "",
                "transcribing": "Der Text erscheint hier Abschnitt für Abschnitt …",
                "interrupted": "Die Sitzung wurde unterbrochen. Audio ist gespeichert – "
                               "„Neu transkribieren“ startet die Transkription.",
                "failed": f"Fehler: {html.escape(s.error)}",
            }.get(s.status, "In dieser Aufnahme wurde keine Sprache erkannt.")
            self.view.setHtml(f"<p style='color:#64748b'>{hint}</p>")
            return
        rows = []
        items = [(seg.start, seg.speaker, seg.text) for seg in segments]
        items += [(t, "⚑", "Marker") for t in s.markers]
        for start, speaker, text in sorted(items, key=lambda i: i[0]):
            color = SPEAKER_COLORS.get(speaker, "#7c3aed")
            rows.append(
                "<tr>"
                f"<td style='color:#94a3b8; padding-right:12px; white-space:nowrap'>{fmt_time(start)}</td>"
                f"<td style='color:{color}; font-weight:600; padding-right:12px; white-space:nowrap'>"
                f"{html.escape(speaker)}</td>"
                f"<td>{html.escape(text)}</td></tr>"
            )
        bar = self.view.verticalScrollBar()
        follow = s.status == "transcribing" and bar.value() >= bar.maximum() - 4
        pos = bar.value()
        self.view.setHtml("<table cellspacing='0' cellpadding='3'>" + "".join(rows) + "</table>")
        bar.setValue(bar.maximum() if follow else pos)

    def _on_progress(self, session_id: str, p) -> None:
        if session_id != self._current_id():
            return
        s = self._sessions.get(session_id)
        if s and s.status != "transcribing":
            self.refresh_sessions()          # status changed (e.g. queued → transcribing)
            return
        self.progress_card.show()
        self.progress_card.update_progress(p)
        now = time.monotonic()
        if p.stage == "done" or now - self._last_render > 1.5:   # partial transcript, throttled
            self._last_render = now
            self._render_current()

    def _on_corrected(self, session_id: str) -> None:
        if session_id == self._current_id():
            self._show_selected()
            self.version_box.setCurrentIndex(1)
            self.toast("KI-korrigierte Fassung gespeichert ✓")

    # --- actions ---------------------------------------------------------------------
    def _copy(self, fmt: str) -> None:
        s = self._current()
        if not s:
            return
        segments = self._segments_for(s)
        if fmt == "times":
            text = copy_with_times(segments)
        elif fmt == "plain":
            text = copy_plain(segments)
        else:
            text = EXPORTERS["md"](s, segments)
        QApplication.clipboard().setText(text)
        self.toast(f"Transkript kopiert ✓  ({len(segments)} Abschnitte)")

    def _export(self, ext: str) -> None:
        s = self._current()
        if not s:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportieren", str(s.folder / f"transkript.{ext}"))
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(EXPORTERS[ext](s, self._segments_for(s)))
            self.toast("Exportiert ✓")

    def _open_folder(self) -> None:
        s = self._current()
        if s:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(s.folder)))

    def _retranscribe(self) -> None:
        s = self._current()
        if s:
            self.controller.transcribe(s)

    def select_session(self, session_id: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == session_id:
                self.list.setCurrentRow(i)
                return

    def closeEvent(self, event) -> None:
        if self.hide_to_tray:
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)
