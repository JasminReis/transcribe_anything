"""Application start: single instance, tray icon, wiring of windows and controller."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from transcribe_anywhere.config import APP_NAME, Settings, config_dir
from transcribe_anywhere.session.store import list_sessions, recover_interrupted
from transcribe_anywhere.ui.controller import Controller
from transcribe_anywhere.ui.main_window import MainWindow
from transcribe_anywhere.ui.pill import RecordingPill
from transcribe_anywhere.ui.settings_dialog import SettingsDialog
from transcribe_anywhere.ui.theme import state_icon

TRAY_TIPS = {"idle": "Transcribe Anywhere – bereit", "recording": "Transcribe Anywhere – Aufnahme läuft",
             "transcribing": "Transcribe Anywhere – transkribiert …"}


class App:
    def __init__(self, qapp: QApplication, settings: Settings):
        self.qapp = qapp
        self.settings = settings
        self.controller = Controller(settings)
        self.window = MainWindow(self.controller)
        self.pill = RecordingPill(self.controller)
        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()

        self.tray = QSystemTrayIcon(state_icon("idle"))
        menu = QMenu()
        self.record_action = menu.addAction("Aufnahme starten", self.toggle_recording)
        menu.addAction("Fenster öffnen", self.show_window)
        menu.addAction("Einstellungen", self.open_settings)
        menu.addSeparator()
        menu.addAction("Beenden", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self.show_window)
        self.tray.setToolTip(TRAY_TIPS["idle"])
        if self.has_tray:
            self.tray.show()
        # Without a tray (e.g. GNOME without AppIndicator) closing the window must quit.
        self.window.hide_to_tray = self.has_tray

        self.window.record_toggled.connect(self.toggle_recording)
        self.window.settings_requested.connect(self.open_settings)
        self.pill.stop_requested.connect(self.toggle_recording)
        self.pill.marker_requested.connect(self.controller.add_marker)
        self.controller.state_changed.connect(self._on_state)
        self.controller.notify.connect(self._notify)
        qapp.aboutToQuit.connect(self.controller.shutdown)

        # Crash recovery + pick up sessions that were recorded but never transcribed
        recovered = recover_interrupted(settings.storage_path)
        for s in list_sessions(settings.storage_path):
            if s.status == "recorded":
                self.controller.transcribe(s)
        self.window.refresh_sessions()
        if recovered:
            self._notify("Unterbrochene Sitzung", f"{len(recovered)} Sitzung(en) wurden unterbrochen. "
                         "Das Audio ist gespeichert und kann transkribiert werden.")

        if not (settings.start_minimized and self.has_tray):
            self.show_window()

    # --- actions ---------------------------------------------------------------
    def toggle_recording(self) -> None:
        if self.controller.state == "recording":
            self.controller.stop_recording()
            return
        if self.settings.consent_reminder:
            box = QMessageBox(QMessageBox.Question, "Aufnahme starten",
                              "Sind alle Teilnehmenden informiert und einverstanden, "
                              "dass das Gespräch aufgezeichnet und transkribiert wird?")
            yes = box.addButton("Ja, aufnehmen", QMessageBox.AcceptRole)
            box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return
        title = self.window.title_edit.text()
        if self.controller.start_recording(title):
            self.window.title_edit.clear()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.window)
        if dialog.exec():
            dialog.apply()
            self.window.refresh_sessions()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def quit(self) -> None:
        if self.controller.state == "recording":
            answer = QMessageBox.question(self.window, "Beenden",
                                          "Eine Aufnahme läuft. Aufnahme beenden und Programm schließen?")
            if answer != QMessageBox.Yes:
                return
        self.window.hide_to_tray = False
        self.qapp.quit()

    # --- reactions -------------------------------------------------------------
    def _on_state(self, state: str) -> None:
        self.tray.setIcon(state_icon(state))
        self.tray.setToolTip(TRAY_TIPS[state])
        self.qapp.setWindowIcon(state_icon(state))
        self.record_action.setText("Aufnahme beenden" if state == "recording" else "Aufnahme starten")
        if state == "recording":
            self.pill.show_at_default_position()
        else:
            self.pill.hide()

    def _notify(self, title: str, message: str) -> None:
        if self.has_tray and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, state_icon(self.controller.state), 6000)
        else:
            self.window.status_label.setText(f"{title}: {message}")

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()


def run() -> int:
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(state_icon("idle"))

    config_dir().mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config_dir() / "instance.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "Transcribe Anywhere läuft bereits (siehe Tray-Symbol).")
        return 0

    app = App(qapp, Settings.load())
    exit_code = qapp.exec()
    del app
    return exit_code
