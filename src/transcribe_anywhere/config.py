"""User settings, stored as JSON in the OS config directory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "Transcribe Anywhere"
APP_DIR = "TranscribeAnywhere"         # folder name: no spaces

SAMPLE_RATE = 16_000          # Whisper works on 16 kHz mono
SEGMENT_SECONDS = 300         # audio files rotate every 5 minutes


def config_dir() -> Path:
    return Path(user_config_dir(APP_DIR, appauthor=False))


def models_dir() -> Path:
    return Path(user_data_dir(APP_DIR, appauthor=False)) / "models"


def default_storage_dir() -> Path:
    return Path(user_data_dir(APP_DIR, appauthor=False)) / "sessions"


@dataclass
class Settings:
    language: str = "de"            # "de" | "en" | "auto"   (Whisper only; Parakeet detects itself)
    engine: str = "auto"            # "auto" (GPU → Whisper, else Parakeet) | "whisper" | "parakeet"
    live: bool = True               # transcribe while recording
    model: str = "auto"             # Whisper model: "auto" | "large-v3-turbo" | "large-v3" | "small"
    compute_device: str = "auto"    # "auto" | "cpu" | "cuda"
    mic_device: str = ""            # "" = OS default microphone
    loopback_device: str = ""       # "" = system audio of the OS default speaker
    storage_dir: str = ""           # "" = default_storage_dir()
    hotwords: str = ""              # names / jargon that should be recognised
    ollama_url: str = "http://localhost:11434"
    llm_model: str = ""             # "" = recommended model for this hardware
    consent_reminder: bool = True
    start_minimized: bool = False

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir) if self.storage_dir else default_storage_dir()

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_dir() / "settings.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), "utf-8")
