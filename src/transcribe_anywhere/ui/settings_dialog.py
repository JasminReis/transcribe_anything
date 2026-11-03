"""Settings window: a sidebar with four pages (recording, transcription, AI, general)."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.config import Settings
from transcribe_anywhere.llm import cloud
from transcribe_anywhere.llm.prompt import DEFAULT_PROMPT, effective_prompt
from transcribe_anywhere.transcription.engine import MODELS
from transcribe_anywhere.ui.theme import STYLE, app_icon

HINT = "color:#64748b; font-size:12px;"

DIALOG_STYLE = STYLE + """
QListWidget#nav { border: none; background: #f1f5f9; padding: 10px 6px; font-size: 14px; outline: 0; }
QListWidget#nav::item { padding: 11px 12px; margin: 2px 0; border-radius: 8px; color: #334155; }
QListWidget#nav::item:hover { background: #e2e8f0; }
QListWidget#nav::item:selected { background: #ede9fe; color: #6d28d9; font-weight: 600; }
QLabel#pageTitle { font-size: 20px; font-weight: 600; }
QLabel#pageSub { color: #64748b; font-size: 13px; }
QGroupBox { font-weight: 600; border: 1px solid #e2e8f0; border-radius: 10px; margin-top: 14px; padding: 14px 10px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QToolButton#advanced { border: none; color: #6d28d9; font-weight: 600; padding: 4px 0; }
QPushButton#secondary { border: 1px solid #cbd5e1; border-radius: 8px; padding: 7px 16px; background: white; }
QPushButton#secondary:hover { background: #f8fafc; }
"""


def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    box = QComboBox()
    for value, label in items:
        box.addItem(label, value)
    idx = box.findData(current)
    box.setCurrentIndex(max(idx, 0))
    return box


def _hint(text: str) -> QLabel:
    label = QLabel(text, wordWrap=True, openExternalLinks=True)
    label.setStyleSheet(HINT)
    return label


def _with_hint(widget: QWidget, hint: str) -> QWidget:
    """A control with a short explanation underneath."""
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 4)
    v.setSpacing(3)
    v.addWidget(widget)
    v.addWidget(_hint(hint))
    return box


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    return form


class PromptEditor(QWidget):
    """Multi-line prompt with a 'restore default' button."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.edit = QPlainTextEdit(effective_prompt(text))
        self.edit.setMinimumHeight(160)
        reset = QPushButton("Standard wiederherstellen", objectName="secondary",
                            clicked=lambda: self.edit.setPlainText(DEFAULT_PROMPT))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_hint("Wird beim Kopieren „mit KI-Prompt“ vor das Transkript gesetzt und an Claude/OpenAI "
                          "geschickt. Das Transkript (mit Uhrzeiten und Sprechern) wird automatisch angehängt."))
        v.addWidget(self.edit, 1)
        v.addLayout(row)

    def value(self) -> str:
        text = self.edit.toPlainText().strip()
        return "" if text == DEFAULT_PROMPT.strip() else text      # "" = follow the default


def _buttons(dialog: QDialog) -> QHBoxLayout:
    save = QPushButton("Speichern", objectName="primary", clicked=dialog.accept)
    save.setDefault(True)
    cancel = QPushButton("Abbrechen", objectName="secondary", clicked=dialog.reject)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(cancel)
    row.addWidget(save)
    return row


class PromptDialog(QDialog):
    """Edit the prompt on its own (from the copy menu)."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt bearbeiten")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(640, 480)
        self.settings = settings
        self.editor = PromptEditor(settings.summary_prompt)
        v = QVBoxLayout(self)
        v.addWidget(self.editor, 1)
        v.addLayout(_buttons(self))

    def apply(self) -> None:
        self.settings.summary_prompt = self.editor.value()
        self.settings.save()


class SettingsDialog(QDialog):
    PAGES = [("🎙", "Aufnahme"), ("📝", "Transkription"), ("✨", "KI"), ("🗂", "Allgemein")]

    def __init__(self, settings: Settings, parent=None, page: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(900, 680)
        self.setMinimumSize(760, 560)
        self.settings = settings

        self.nav = QListWidget(objectName="nav")
        self.nav.setFixedWidth(200)
        self.stack = QStackedWidget()
        builders = [self._recording_page, self._transcription_page, self._ai_page, self._general_page]
        for (icon, name), build in zip(self.PAGES, builders):
            self.nav.addItem(f"{icon}   {name}")
            scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
            scroll.setWidget(build())
            self.stack.addWidget(scroll)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(page)

        right = QVBoxLayout()
        right.setContentsMargins(20, 16, 20, 16)
        right.addWidget(self.stack, 1)
        right.addLayout(_buttons(self))
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.nav)
        root.addLayout(right, 1)

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 0, 8, 0)
        v.addWidget(QLabel(title, objectName="pageTitle"))
        sub = QLabel(subtitle, objectName="pageSub", wordWrap=True)
        v.addWidget(sub)
        v.addSpacing(6)
        return page, v

    # --- pages ------------------------------------------------------------------
    def _recording_page(self) -> QWidget:
        s = self.settings
        try:
            from transcribe_anywhere.audio.devices import list_inputs

            devices = list_inputs()
        except Exception:
            devices = []
        mics = [("", "Systemstandard")] + [(d.id, d.name) for d in devices if not d.is_loopback]
        loops = [("", "Systemstandard (Standard-Lautsprecher)")] + [
            (d.id, d.name) for d in devices if d.is_loopback
        ]
        self.mode = _combo([("online", "💻  Online-Meeting (Teams, Zoom, Meet …)"),
                            ("inperson", "🤝  Vor Ort – zwei Mikrofone (Interview, Kundentermin)")],
                           s.recording_mode)
        self.mic = _combo(mics, s.mic_device)
        self.mic2 = _combo([("", "– bitte wählen –")] + mics[1:], s.mic2_device)
        self.loopback = _combo(loops, s.loopback_device)
        self.live = QCheckBox("Während der Aufnahme live mitschreiben", checked=s.live)
        self.consent = QCheckBox("Vor jeder Aufnahme an die Einwilligung erinnern", checked=s.consent_reminder)

        page, v = self._page("Aufnahme", "Welche Geräte aufgenommen werden und was beim Start passiert.")
        form = _form()
        form.addRow("Modus", _with_hint(self.mode, "Auch oben neben „Aufnahme starten“ umschaltbar."))
        self._mic_hint = _hint("")
        mic_box = QWidget()
        mb = QVBoxLayout(mic_box)
        mb.setContentsMargins(0, 0, 0, 4)
        mb.setSpacing(3)
        mb.addWidget(self.mic)
        mb.addWidget(self._mic_hint)
        self._mic_label = QLabel("Mikrofon")
        form.addRow(self._mic_label, mic_box)
        self._mic2_row = _with_hint(self.mic2, "Das Mikrofon der anderen Person. Am besten steht vor jeder Person "
                                               "ein eigenes Mikrofon (Ansteck- oder Tischmikrofon): Das Programm "
                                               "trennt die Stimmen nach Lautstärke, so erscheint nichts doppelt.")
        form.addRow("Mikrofon 2 (Gast)", self._mic2_row)
        self._loop_row = _with_hint(
            self.loopback, "Der Ton der anderen (Teams, Zoom, Meet …) – das Gerät, auf dem du sie hörst.")
        form.addRow("Systemaudio", self._loop_row)
        self._rec_form = form
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()
        form.addRow("", _with_hint(self.live, "Der Text erscheint schon während des Meetings."))
        form.addRow("", _with_hint(self.consent, "Fragt vor dem Start, ob alle einverstanden sind."))
        v.addLayout(form)
        v.addStretch(1)
        return page

    def _mode_changed(self) -> None:
        inperson = self.mode.currentData() == "inperson"
        self._mic_label.setText("Mikrofon 1 (Ich)" if inperson else "Mikrofon")
        self._mic_hint.setText("Dein Mikrofon." if inperson else
                               "Deine eigene Stimme. Ein Headset vermeidet doppelten Text.")
        self._rec_form.setRowVisible(self._mic2_row, inperson)
        self._rec_form.setRowVisible(self._loop_row, not inperson)

    def _transcription_page(self) -> QWidget:
        s = self.settings
        self.engine = _combo([("auto", "Automatisch (empfohlen)"),
                              ("parakeet", "Parakeet v3 – schnell, ideal für Laptops"),
                              ("whisper", "Whisper – genauer, braucht eine NVIDIA-Grafikkarte für Live")], s.engine)
        self.speakers = QCheckBox("Andere Teilnehmende unterscheiden („Sprecher 1“, „Sprecher 2“ …)",
                                  checked=s.speaker_detection)
        self.hotwords = QLineEdit(s.hotwords, placeholderText="z. B. Ehrenfried, Kubernetes, Q3-Roadmap")
        self.language = _combo([("de", "Deutsch"), ("en", "Englisch"), ("auto", "Automatisch")], s.language)
        self.model = _combo([("auto", "Automatisch (large-v3-turbo)")] + [(m, m) for m in MODELS], s.model)
        self.device = _combo(
            [("auto", "Automatisch (GPU wenn verfügbar)"), ("cpu", "Prozessor (CPU)"), ("cuda", "NVIDIA-Grafikkarte")],
            s.compute_device,
        )

        page, v = self._page("Transkription", "Wie aus der Aufnahme Text wird.")
        form = _form()
        form.addRow("Spracherkennung", _with_hint(
            self.engine, "„Automatisch“ wählt das passende Verfahren für dieses Gerät."))
        form.addRow("", _with_hint(self.speakers, "Läuft nach dem Transkript, offline. Namen trägst du im "
                                                  "Transkript per Klick auf den Sprecher ein."))
        form.addRow("Fachbegriffe", _with_hint(
            self.hotwords, "Namen und Begriffe, die richtig geschrieben werden sollen (mit Komma trennen)."))
        v.addLayout(form)

        toggle = QToolButton(objectName="advanced", text="▸  Erweitert", checkable=True)
        toggle.setCursor(Qt.PointingHandCursor)
        advanced = QWidget()
        adv = _form()
        adv.setContentsMargins(0, 0, 0, 0)
        adv.addRow("Sprache (Whisper)", self.language)
        adv.addRow("Whisper-Modell", self.model)
        adv.addRow("Rechenwerk", _with_hint(self.device, "Auf Laptops ohne NVIDIA-Grafikkarte: Prozessor (CPU)."))
        advanced.setLayout(adv)
        advanced.hide()
        toggle.toggled.connect(lambda on: (advanced.setVisible(on),
                                           toggle.setText(("▾" if on else "▸") + "  Erweitert")))
        v.addSpacing(6)
        v.addWidget(toggle, 0, Qt.AlignLeft)
        v.addWidget(advanced)
        v.addStretch(1)
        return page

    def _ai_page(self) -> QWidget:
        s = self.settings
        page, v = self._page("KI", "Meetings automatisch zusammenfassen – alles optional.")
        self.prompt = PromptEditor(s.summary_prompt)
        prompt_box = QGroupBox("Prompt für die Zusammenfassung")
        QVBoxLayout(prompt_box).addWidget(self.prompt)

        # cloud AI
        self._keys = {p: cloud.get_key(p) for p in cloud.PROVIDERS}
        self._provider_shown = ""
        self.provider = _combo([("", "Aus")] + list(cloud.PROVIDERS.items()), s.cloud_provider)
        self.api_key = QLineEdit(echoMode=QLineEdit.Password, placeholderText="API-Schlüssel einfügen")
        self.key_link = _hint("")
        self.cloud_model = QComboBox(editable=True)
        self.cloud_model.setMinimumWidth(240)
        self.check_btn = QPushButton("Prüfen und Modelle laden", objectName="secondary", clicked=self._load_models)
        self.cloud_status = _hint("")
        model_row = QWidget()
        mh = QHBoxLayout(model_row)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.addWidget(self.cloud_model, 1)
        mh.addWidget(self.check_btn)
        cloud_box = QGroupBox("Cloud-KI: Claude oder OpenAI")
        cf = _form()
        cf.addRow("Anbieter", self.provider)
        cf.addRow("API-Schlüssel", self.api_key)
        cf.addRow("", self.key_link)
        cf.addRow("Modell", model_row)
        cf.addRow("", self.cloud_status)
        self._cloud_info = _hint("Ein API-Schlüssel ist nicht dasselbe wie ein Abo: Claude Pro/Max und ChatGPT Plus "
                            "enthalten keinen API-Zugang. Die API wird pro Nutzung abgerechnet (eine Zusammenfassung "
                            "kostet meist nur Cent-Beträge). Zur Auswertung wird das Transkript an den Anbieter "
                            "gesendet. Der Schlüssel wird in der Windows-Anmeldeinformationsverwaltung gespeichert.")
        cf.addRow("", self._cloud_info)
        cloud_box.setLayout(cf)
        self._cloud_form = cf
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self._provider_changed()

        # local AI
        self.local_ai = QCheckBox("Lokale KI (Ollama) im Tab „KI-Auswertung“ anzeigen", checked=s.local_ai)
        self.ollama_url = QLineEdit(s.ollama_url, placeholderText="http://localhost:11434")
        local_box = QGroupBox("Lokale KI (offline)")
        lf = _form()
        lf.addRow("", _with_hint(self.local_ai, "Läuft komplett auf diesem Gerät, braucht aber "
                                                "<a href='https://ollama.com/download'>Ollama</a> und ist auf "
                                                "Laptops langsam."))
        lf.addRow("Ollama-Adresse", self.ollama_url)
        local_box.setLayout(lf)
        self.local_ai.toggled.connect(self.ollama_url.setEnabled)
        self.ollama_url.setEnabled(s.local_ai)

        v.addWidget(cloud_box)
        v.addWidget(prompt_box)
        v.addWidget(local_box)
        v.addStretch(1)
        return page

    def _general_page(self) -> QWidget:
        s = self.settings
        self.storage = QLineEdit(str(s.storage_path))
        browse = QPushButton("Ändern …", objectName="secondary", clicked=self._browse)
        storage_row = QWidget()
        h = QHBoxLayout(storage_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.storage, 1)
        h.addWidget(browse)
        self.minimized = QCheckBox("Minimiert im Tray starten", checked=s.start_minimized)

        page, v = self._page("Allgemein", "Speicherort und Programmstart.")
        form = _form()
        form.addRow("Speicherort", _with_hint(storage_row, "Hier liegen Aufnahmen, Transkripte und "
                                                           "Zusammenfassungen."))
        form.addRow("", _with_hint(self.minimized, "Beim Start nur das Symbol neben der Uhr zeigen."))
        if sys.platform == "win32":
            shortcut_btn = QPushButton("  Verknüpfungen anlegen", objectName="secondary", clicked=self._shortcuts)
            shortcut_btn.setIcon(app_icon())
            self.shortcut_status = _hint("Legt „Transcribe Anywhere“ mit eigenem Symbol auf dem Desktop und im "
                                         "Startmenü an. Danach: Rechtsklick auf das Symbol → „An Taskleiste "
                                         "anheften“. Oder bei laufendem Programm: Rechtsklick auf sein Symbol in "
                                         "der Taskleiste → „An Taskleiste anheften“.")
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 4)
            bv.setSpacing(4)
            bv.addWidget(shortcut_btn, 0, Qt.AlignLeft)
            bv.addWidget(self.shortcut_status)
            form.addRow("Taskleiste", box)
        v.addLayout(form)
        v.addStretch(1)
        return page

    def _shortcuts(self) -> None:
        from transcribe_anywhere import winshortcut

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            winshortcut.create_shortcuts()
        except Exception as e:
            self.shortcut_status.setText(f"<span style='color:#dc2626'>✗ {e}</span>")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.shortcut_status.setText("<span style='color:#16a34a'>✓ Auf dem Desktop und im Startmenü angelegt.</span>"
                                     " Jetzt Rechtsklick auf das Desktop-Symbol → „An Taskleiste anheften“ "
                                     "(unter Windows 11 ggf. erst „Weitere Optionen anzeigen“).")

    # --- cloud helpers ------------------------------------------------------------
    def _provider_changed(self) -> None:
        if self._provider_shown:                       # keep what was typed for the previous provider
            self._keys[self._provider_shown] = self.api_key.text().strip()
        provider = self.provider.currentData()
        self._provider_shown = provider
        enabled = bool(provider)
        for w in (self.api_key, self.cloud_model.parentWidget(), self.cloud_status, self._cloud_info):
            self._cloud_form.setRowVisible(w, enabled)      # only show what is needed
        self.api_key.setText(self._keys.get(provider, "") if provider else "")
        self.cloud_model.clear()
        self.cloud_status.clear()
        if not provider:
            self.key_link.setText("Aus: Es wird nichts ins Internet gesendet.")
            return
        self.key_link.setText(f"Schlüssel erstellen: <a href='{cloud.KEY_PAGES[provider]}'>"
                              f"{cloud.KEY_PAGES[provider].split('//')[1]}</a>")
        current = self.settings.cloud_model if provider == self.settings.cloud_provider else ""
        default = cloud.default_model(provider)
        self.cloud_model.addItem("Automatisch (neuestes Modell)" if not default else f"{default} (empfohlen)",
                                 default)
        if current and current != default:
            self.cloud_model.addItem(current, current)
            self.cloud_model.setCurrentIndex(1)

    def _load_models(self) -> None:
        provider, key = self.provider.currentData(), self.api_key.text().strip()
        if not key:
            self.cloud_status.setText("<span style='color:#dc2626'>Bitte zuerst einen API-Schlüssel einfügen.</span>")
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            models = cloud.list_models(provider, key)
        except cloud.CloudError as e:
            self.cloud_status.setText(f"<span style='color:#dc2626'>✗ {e}</span>")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        keep = self._chosen_model()
        default = cloud.default_model(provider)
        self.cloud_model.clear()
        self.cloud_model.addItem(f"{default} (empfohlen)" if default else "Automatisch (neuestes Modell)", default)
        for m in models:
            if m != default:
                self.cloud_model.addItem(m, m)
        idx = self.cloud_model.findData(keep)
        self.cloud_model.setCurrentIndex(max(idx, 0))
        self.cloud_status.setText(f"<span style='color:#16a34a'>✓ Schlüssel funktioniert · "
                                  f"{len(models)} Modelle verfügbar</span>")

    def _chosen_model(self) -> str:
        idx = self.cloud_model.currentIndex()
        typed = self.cloud_model.currentText().strip()
        if idx >= 0 and self.cloud_model.itemText(idx) == typed:
            return self.cloud_model.itemData(idx) or ""
        return typed                                   # a model id typed by hand

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Speicherort wählen", self.storage.text())
        if folder:
            self.storage.setText(folder)

    def apply(self) -> None:
        s = self.settings
        s.engine = self.engine.currentData()
        s.live = self.live.isChecked()
        s.speaker_detection = self.speakers.isChecked()
        s.language = self.language.currentData()
        s.model = self.model.currentData()
        s.compute_device = self.device.currentData()
        s.mic_device = self.mic.currentData()
        s.recording_mode = self.mode.currentData()
        s.mic2_device = self.mic2.currentData()
        s.loopback_device = self.loopback.currentData()
        s.hotwords = self.hotwords.text()
        s.storage_dir = self.storage.text().strip()
        s.consent_reminder = self.consent.isChecked()
        s.start_minimized = self.minimized.isChecked()
        s.summary_prompt = self.prompt.value()
        s.local_ai = self.local_ai.isChecked()
        s.ollama_url = self.ollama_url.text().strip() or "http://localhost:11434"
        provider = self.provider.currentData()
        if provider:
            self._keys[provider] = self.api_key.text().strip()
        for p, key in self._keys.items():
            if key != cloud.get_key(p):
                cloud.set_key(p, key)
        s.cloud_provider = provider
        s.cloud_model = self._chosen_model() if provider else ""
        s.save()
