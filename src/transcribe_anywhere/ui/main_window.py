"""Main window: record button, session library, transcript + AI tabs."""

from __future__ import annotations

import html
import time

from PySide6.QtCore import QPropertyAnimation, QSequentialAnimationGroup, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.llm.prompt import effective_prompt
from transcribe_anywhere.session.export import (
    EXPORTERS,
    copy_plain,
    copy_with_prompt,
    copy_with_times,
    fmt_date,
    fmt_duration,
)
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.store import list_sessions
from transcribe_anywhere.session.transcript import Segment, read_segments
from transcribe_anywhere.ui.ai_panel import AiPanel
from transcribe_anywhere.ui.progress_card import ProgressCard
from transcribe_anywhere.ui.settings_dialog import PromptDialog
from transcribe_anywhere.ui.theme import SPEAKER_COLORS, STYLE, gear_icon

STATUS_ICONS = {
    "recording": "🔴", "recorded": "⏳", "transcribing": "⏳",
    "done": "✓", "interrupted": "⚠", "failed": "✗",
}


# Colours for "Sprecher 1", "Sprecher 2" … (in order)
OTHER_COLORS = ["#16a34a", "#db2777", "#0891b2", "#ca8a04", "#9333ea", "#ea580c", "#4f46e5", "#0d9488"]


def speaker_color(label: str) -> str:
    if label in SPEAKER_COLORS:
        return SPEAKER_COLORS[label]
    if label.startswith("Sprecher "):
        try:
            return OTHER_COLORS[(int(label.split()[1]) - 1) % len(OTHER_COLORS)]
        except ValueError:
            pass
    return "#7c3aed"


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
        self.mode_box = QComboBox(objectName="modeBox")
        self.mode_box.addItem("💻  Online-Meeting", "online")
        self.mode_box.addItem("🤝  Vor Ort · 2 Mikrofone", "inperson")
        self.mode_box.setToolTip("Online: dein Mikrofon + Ton des Meetings (Teams, Zoom …)\n"
                                 "Vor Ort: zwei Mikrofone, eins pro Person (z. B. Interview, Kundentermin)")
        self.mode_box.setCursor(Qt.PointingHandCursor)
        self._sync_mode()
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.title_edit = QLineEdit(placeholderText="Meeting-Titel (optional)")
        self.title_edit.setMinimumWidth(280)
        self.status_label = QLabel("Bereit")
        self.status_label.setStyleSheet("color: #64748b;")
        # (connect via lambda: PySide6 6.11 ignores a signal passed as clicked=…)
        settings_btn = QPushButton(" Einstellungen", objectName="settingsButton")
        settings_btn.setIcon(gear_icon())
        settings_btn.setIconSize(QSize(18, 18))
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setToolTip("Mikrofon, Spracherkennung, KI und mehr  (Strg+,)")
        settings_btn.clicked.connect(lambda: self.settings_requested.emit())
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.settings_requested.emit())
        top = QHBoxLayout()
        top.addWidget(self.record_button)
        top.addWidget(self.mode_box)
        top.addWidget(self.title_edit)
        top.addWidget(self.status_label, 1)
        top.addWidget(settings_btn)

        # --- left: session library
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        QShortcut(QKeySequence.Delete, self.list, activated=self._delete)
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
        copy_menu.addSeparator()
        copy_menu.addAction("✨ Mit KI-Prompt (zum Einfügen in ChatGPT, Claude …)", lambda: self._copy("prompt"))
        copy_menu.addAction("Prompt bearbeiten …", self._edit_prompt)
        self.copy_btn.setMenu(copy_menu)

        self.export_btn = QToolButton(text="Export ▾", popupMode=QToolButton.InstantPopup)
        menu = QMenu(self.export_btn)
        for ext, label in (("txt", "Text (.txt)"), ("md", "Markdown (.md)"), ("srt", "Untertitel (.srt)")):
            menu.addAction(label, lambda e=ext: self._export(e))
        self.export_btn.setMenu(menu)
        self.folder_btn = QPushButton("Ordner öffnen", clicked=self._open_folder)
        self.retranscribe_btn = QToolButton(text="Neu transkribieren", popupMode=QToolButton.MenuButtonPopup)
        self.retranscribe_btn.clicked.connect(lambda: self._retranscribe(None))
        rmenu = QMenu(self.retranscribe_btn)
        rmenu.addAction("Mit Whisper (genauer, auf CPU langsam)", lambda: self._retranscribe("whisper"))
        rmenu.addAction("Mit Parakeet (schnell)", lambda: self._retranscribe("parakeet"))
        rmenu.addSeparator()
        self.speakers_action = rmenu.addAction("Nur Sprecher neu erkennen", self._detect_speakers)
        self.retranscribe_btn.setMenu(rmenu)
        self.delete_btn = QPushButton("🗑  Löschen", clicked=self._delete)
        self.delete_btn.setToolTip("Aufnahme und Transkript in den Papierkorb verschieben (Entf)")
        self.version_box = QComboBox()
        self.version_box.addItem("Original", "original")
        self.version_box.addItem("✨ KI-korrigiert", "corrected")
        self.version_box.setMinimumWidth(150)
        self.version_box.currentIndexChanged.connect(lambda *_: self._render_current())
        actions = QHBoxLayout()
        for w in (self.copy_btn, self.export_btn, self.folder_btn, self.retranscribe_btn, self.delete_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(self.version_box)

        self.progress_card = ProgressCard()
        self.progress_card.hide()
        self.view = QTextBrowser(openExternalLinks=False, openLinks=False)
        self.view.setStyleSheet("QTextBrowser { font-size: 14px; padding: 8px; }")
        self.view.anchorClicked.connect(self._on_anchor)
        self.speaker_hint = QLabel("Tipp: Auf einen Sprecher klicken, um einen Namen einzutragen.")
        self.speaker_hint.setStyleSheet("color:#94a3b8; font-size: 12px;")
        self.speaker_hint.hide()

        transcript_tab = QWidget()
        tv = QVBoxLayout(transcript_tab)
        tv.setContentsMargins(0, 8, 0, 0)
        tv.addLayout(actions)
        tv.addWidget(self.progress_card)
        tv.addWidget(self.speaker_hint)
        tv.addWidget(self.view, 1)

        # --- tab 2: AI
        self.ai = AiPanel(controller.settings)
        self.ai.corrected.connect(self._on_corrected)

        self.tabs = QTabWidget(documentMode=True)
        self.tabs.addTab(transcript_tab, "Transkript")
        self.tabs.addTab(self.ai, "✨ KI-Auswertung")
        self.tabs.setTabVisible(1, self.ai.any_enabled)

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

    def _sync_mode(self) -> None:
        self.mode_box.blockSignals(True)
        self.mode_box.setCurrentIndex(max(self.mode_box.findData(self.controller.settings.recording_mode), 0))
        self.mode_box.blockSignals(False)

    def _mode_changed(self) -> None:
        settings = self.controller.settings
        settings.recording_mode = self.mode_box.currentData()
        settings.save()
        if settings.recording_mode == "inperson" and not settings.mic2_device:
            self.toast("Vor Ort: Bitte noch das zweite Mikrofon wählen")
            self.settings_requested.emit()          # opens on the "Aufnahme" page
        elif settings.recording_mode == "inperson":
            self.toast("Vor Ort: zwei Mikrofone – „Ich“ und „Gast“")
        else:
            self.toast("Online-Meeting: Mikrofon + Ton des Meetings")

    def apply_settings(self) -> None:
        """Called after the settings dialog was saved."""
        self._sync_mode()
        self.ai.refresh()
        self.tabs.setTabVisible(1, self.ai.any_enabled)
        self.refresh_sessions()

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
        self.mode_box.setEnabled(not recording)
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
        if s.speakers == "pending":
            meta += " · Sprecher werden erkannt …"
        elif s.speakers == "failed":
            meta += " · Sprechererkennung fehlgeschlagen"
        return meta

    def _show_selected(self) -> None:
        s = self._current()
        for w in (self.copy_btn, self.export_btn, self.folder_btn, self.retranscribe_btn, self.delete_btn):
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
        self.delete_btn.setEnabled(self.controller.can_delete(s))
        self.speakers_action.setEnabled(s.status == "done" and s.speakers != "pending")
        self.copy_btn.setEnabled(s.transcript_path.exists())
        has_corrected = s.corrected_path.exists()
        self.version_box.setVisible(has_corrected)
        if not has_corrected:
            self.version_box.setCurrentIndex(0)
        live = s.status == "recording" and self.controller.settings.live
        if s.status in ("recorded", "transcribing") or live:
            if s.status == "recorded" or (live and self.controller.live_progress is None):
                self.progress_card.set_queued(live=live)
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
                "recording": ("Live-Transkription läuft – der Text erscheint hier nach den ersten Sätzen."
                              if self.controller.settings.live else
                              "Aufnahme läuft. Das Transkript erscheint nach dem Beenden."),
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
            color = speaker_color(speaker)
            name = html.escape(s.speaker_name(speaker))
            if speaker != "⚑":       # click a speaker to give them a name
                name = (f"<a href='speaker:{html.escape(speaker)}' style='color:{color}; "
                        f"text-decoration:none'>{name}</a>")
            rows.append(
                "<tr>"
                f"<td style='color:#94a3b8; padding-right:12px; white-space:nowrap'>{s.clock(start)}</td>"
                f"<td style='color:{color}; font-weight:600; padding-right:12px; white-space:nowrap'>"
                f"{name}</td>"
                f"<td>{html.escape(text)}</td></tr>"
            )
        self.speaker_hint.setVisible(any(seg.speaker.startswith("Sprecher ") for seg in segments)
                                     and not s.speaker_names)
        bar = self.view.verticalScrollBar()
        follow = s.status in ("recording", "transcribing") and bar.value() >= bar.maximum() - 4
        pos = bar.value()
        self.view.setHtml("<table cellspacing='0' cellpadding='3'>" + "".join(rows) + "</table>")
        bar.setValue(bar.maximum() if follow else pos)

    def _on_progress(self, session_id: str, p) -> None:
        if session_id != self._current_id():
            return
        s = self._sessions.get(session_id)
        if s and s.status not in ("recording", "transcribing"):
            self.refresh_sessions()          # status changed (e.g. queued → transcribing)
            return
        self.progress_card.show()
        self.progress_card.update_progress(p)
        if p.done_seconds and not self.copy_btn.isEnabled():
            self.copy_btn.setEnabled(True)       # copying works mid-meeting, too
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
            text = copy_with_times(s, segments)
        elif fmt == "plain":
            text = copy_plain(s, segments)
        elif fmt == "prompt":
            text = copy_with_prompt(effective_prompt(self.controller.settings.summary_prompt), s, segments)
        else:
            text = EXPORTERS["md"](s, segments)
        QApplication.clipboard().setText(text)
        if fmt == "prompt":
            self.toast("Prompt + Transkript kopiert ✓  – jetzt in ChatGPT, Claude o. Ä. einfügen")
        else:
            self.toast(f"Transkript kopiert ✓  ({len(segments)} Abschnitte)")

    def _edit_prompt(self) -> None:
        dialog = PromptDialog(self.controller.settings, self)
        if dialog.exec():
            dialog.apply()
            self.toast("Prompt gespeichert ✓")

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

    def _retranscribe(self, engine: str | None) -> None:
        s = self._current()
        if s:
            self.controller.transcribe(s, engine)

    def _detect_speakers(self) -> None:
        s = self._current()
        if s:
            self.controller.detect_speakers(s)

    def _on_anchor(self, url: QUrl) -> None:
        text = url.toString()
        if not text.startswith("speaker:"):
            return
        label = text[len("speaker:"):]
        s = self._current()
        if not s:
            return
        name, ok = QInputDialog.getText(self, "Sprecher benennen",
                                        f"Name für „{label}“ (leer lassen = „{label}“):",
                                        text=s.speaker_names.get(label, ""))
        if ok:
            self.controller.rename_speaker(s, label, name)

    def _list_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        self.list.setCurrentItem(item)
        menu = QMenu(self)
        delete = menu.addAction("🗑  Löschen", self._delete)
        s = self._current()
        delete.setEnabled(bool(s and self.controller.can_delete(s)))
        menu.addAction("Ordner öffnen", self._open_folder)
        menu.exec(self.list.mapToGlobal(pos))

    def _delete(self) -> None:
        s = self._current()
        if not s:
            return
        if not self.controller.can_delete(s):
            self.toast("Läuft gerade – bitte warten, bis Aufnahme bzw. Transkription fertig ist.")
            return
        box = QMessageBox(QMessageBox.Warning, "Sitzung löschen",
                          f"„{s.title}“ ({fmt_date(s.started_at)}) löschen?\n\n"
                          "Audio, Transkript und Zusammenfassung werden in den Papierkorb verschoben.", parent=self)
        yes = box.addButton("Löschen", QMessageBox.DestructiveRole)
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        row = self.list.currentRow()
        if self.controller.delete_session(s):
            self.list.setCurrentRow(min(row, self.list.count() - 1))
            self.toast("Sitzung gelöscht ✓  (im Papierkorb)")
        else:
            self.toast("Konnte nicht gelöscht werden – ist eine Datei noch geöffnet?")

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
