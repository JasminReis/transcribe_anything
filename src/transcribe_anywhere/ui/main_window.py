"""Main window: record button, session library, transcript view."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.session.export import EXPORTERS, fmt_date, fmt_duration, fmt_time
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.store import list_sessions
from transcribe_anywhere.session.transcript import read_segments
from transcribe_anywhere.ui.theme import SPEAKER_COLORS, STYLE

STATUS_ICONS = {
    "recording": "🔴", "recorded": "⏳", "transcribing": "⏳",
    "done": "✓", "interrupted": "⚠", "failed": "✗",
}


class MainWindow(QMainWindow):
    record_toggled = Signal()
    settings_requested = Signal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Transcribe Anywhere")
        self.resize(1100, 700)
        self.setStyleSheet(STYLE)
        self._sessions: dict[str, Session] = {}
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

        # --- right: transcript
        self.session_title = QLabel()
        self.session_title.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.session_meta = QLabel()
        self.session_meta.setStyleSheet("color: #64748b;")
        self.progress = QProgressBar(textVisible=True)
        self.progress.hide()

        export_btn = QToolButton(text="Export ▾", popupMode=QToolButton.InstantPopup)
        menu = QMenu(export_btn)
        for ext, label in (("txt", "Text (.txt)"), ("md", "Markdown (.md)"), ("srt", "Untertitel (.srt)")):
            menu.addAction(label, lambda e=ext: self._export(e))
        export_btn.setMenu(menu)
        self.export_btn = export_btn
        self.folder_btn = QPushButton("Ordner öffnen", clicked=self._open_folder)
        self.retranscribe_btn = QPushButton("Neu transkribieren", clicked=self._retranscribe)
        actions = QHBoxLayout()
        for w in (export_btn, self.folder_btn, self.retranscribe_btn):
            actions.addWidget(w)
        actions.addStretch(1)

        self.view = QTextBrowser(openExternalLinks=False)
        self.view.setStyleSheet("QTextBrowser { font-size: 14px; padding: 8px; }")

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.addWidget(self.session_title)
        rv.addWidget(self.session_meta)
        rv.addLayout(actions)
        rv.addWidget(self.progress)
        rv.addWidget(self.view, 1)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 800])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        controller.sessions_changed.connect(self.refresh_sessions)
        controller.state_changed.connect(self.set_state)
        controller.progress.connect(self._on_progress)
        controller.status.connect(self.status_label.setText)
        self.refresh_sessions()
        self.set_state(controller.state)

    # --- state ---------------------------------------------------------------
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

    # --- library ---------------------------------------------------------------
    def refresh_sessions(self) -> None:
        current = self._current_id()
        self.list.blockSignals(True)
        self.list.clear()
        self._sessions = {}
        for s in list_sessions(self.controller.settings.storage_path):
            self._sessions[s.id] = s
            when = fmt_date(s.started_at)
            dur = fmt_duration(s.duration) if s.duration else "–"
            item = QListWidgetItem(f"{s.title}\n{when} · {dur} · {STATUS_ICONS.get(s.status, '')} {s.status_label}")
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
        sid = self._current_id()
        if not sid:
            return None
        s = self._sessions.get(sid)
        return Session.load(s.folder) if s else None

    def _show_selected(self) -> None:
        s = self._current()
        has = s is not None
        for w in (self.export_btn, self.folder_btn, self.retranscribe_btn):
            w.setEnabled(has)
        if not s:
            self.session_title.setText("Noch keine Sitzungen")
            self.session_meta.setText("Starte eine Aufnahme – das Transkript erscheint hier.")
            self.view.clear()
            return
        self.session_title.setText(s.title)
        meta = f"{fmt_date(s.started_at)} · {fmt_duration(s.duration)} · {s.status_label}"
        if s.model:
            meta += f" · {s.model}"
        self.session_meta.setText(meta)
        busy = s.status in ("recording", "recorded", "transcribing")
        self.retranscribe_btn.setEnabled(not busy)
        if s.status != "transcribing":
            self.progress.hide()
        self._render(s)

    def _render(self, s: Session) -> None:
        segments = read_segments(s.transcript_path)
        if not segments:
            hint = {
                "recording": "Aufnahme läuft. Das Transkript erscheint nach dem Beenden.",
                "recorded": "Wartet auf Transkription …",
                "transcribing": "Wird transkribiert …",
                "interrupted": "Die Sitzung wurde unterbrochen. Audio ist gespeichert – "
                "„Neu transkribieren“ startet die Transkription.",
                "failed": f"Fehler: {html.escape(s.error)}",
            }.get(s.status, "Kein Text erkannt.")
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
        at_end = bar.value() >= bar.maximum() - 4
        pos = bar.value()
        self.view.setHtml("<table cellspacing='0' cellpadding='3'>" + "".join(rows) + "</table>")
        bar.setValue(bar.maximum() if at_end and s.status == "transcribing" else pos)

    def _on_progress(self, session_id: str, done: int, total: int) -> None:
        if session_id != self._current_id():
            self.refresh_sessions()
            return
        self.progress.show()
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(f"Transkription: %p %  ({done}/{total} Abschnitte)")
        else:
            self.progress.setRange(0, 0)   # busy indicator while the model loads
        s = self._current()
        if s:
            self._render(s)
            self.session_meta.setText(f"{fmt_date(s.started_at)} · {fmt_duration(s.duration)} · {s.status_label}")

    # --- actions ---------------------------------------------------------------
    def _export(self, ext: str) -> None:
        s = self._current()
        if not s:
            return
        default = str(s.folder / f"transkript.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, "Exportieren", default)
        if path:
            text = EXPORTERS[ext](s, read_segments(s.transcript_path))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

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
