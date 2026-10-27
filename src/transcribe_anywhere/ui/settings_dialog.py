"""Settings dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from transcribe_anywhere.config import Settings
from transcribe_anywhere.transcription.engine import MODELS


def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    box = QComboBox()
    for value, label in items:
        box.addItem(label, value)
    idx = box.findData(current)
    box.setCurrentIndex(max(idx, 0))
    return box


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(520)
        self.settings = settings

        try:
            from transcribe_anywhere.audio.devices import list_inputs

            devices = list_inputs()
        except Exception:
            devices = []
        mics = [("", "Systemstandard")] + [(d.id, d.name) for d in devices if not d.is_loopback]
        loops = [("", "Systemstandard (Standard-Lautsprecher)")] + [
            (d.id, d.name) for d in devices if d.is_loopback
        ]

        self.language = _combo([("de", "Deutsch"), ("en", "Englisch"), ("auto", "Automatisch")], settings.language)
        self.model = _combo([("auto", "Automatisch (large-v3-turbo)")] + [(m, m) for m in MODELS], settings.model)
        self.device = _combo(
            [("auto", "Automatisch (GPU wenn verfügbar)"), ("cpu", "CPU"), ("cuda", "NVIDIA GPU")],
            settings.compute_device,
        )
        self.mic = _combo(mics, settings.mic_device)
        self.loopback = _combo(loops, settings.loopback_device)
        self.hotwords = QLineEdit(settings.hotwords, placeholderText="z. B. Ehrenfried, Kubernetes, Q3-Roadmap")
        self.hotwords.setToolTip("Hilft der Spracherkennung und der KI-Korrektur bei Namen und Fachbegriffen.")
        self.storage = QLineEdit(str(settings.storage_path))
        browse = QPushButton("…", clicked=self._browse)
        storage_row = QWidget()
        h = QHBoxLayout(storage_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.storage)
        h.addWidget(browse)
        self.ollama_url = QLineEdit(settings.ollama_url, placeholderText="http://localhost:11434")
        self.consent = QCheckBox("Vor jeder Aufnahme an die Einwilligung erinnern", checked=settings.consent_reminder)
        self.minimized = QCheckBox("Minimiert im Tray starten", checked=settings.start_minimized)

        form = QFormLayout(self)
        form.addRow("Sprache", self.language)
        form.addRow("Modell", self.model)
        form.addRow("Rechenwerk", self.device)
        form.addRow("Mikrofon", self.mic)
        form.addRow("Systemaudio", self.loopback)
        form.addRow("Fachbegriffe", self.hotwords)
        form.addRow("Speicherort", storage_row)
        form.addRow("Ollama (lokale KI)", self.ollama_url)
        form.addRow("", self.consent)
        form.addRow("", self.minimized)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Speicherort wählen", self.storage.text())
        if folder:
            self.storage.setText(folder)

    def apply(self) -> None:
        s = self.settings
        s.language = self.language.currentData()
        s.model = self.model.currentData()
        s.compute_device = self.device.currentData()
        s.mic_device = self.mic.currentData()
        s.loopback_device = self.loopback.currentData()
        s.hotwords = self.hotwords.text()
        s.storage_dir = self.storage.text().strip()
        s.ollama_url = self.ollama_url.text().strip() or "http://localhost:11434"
        s.consent_reminder = self.consent.isChecked()
        s.start_minimized = self.minimized.isChecked()
        s.save()
