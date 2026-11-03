"""One recorded meeting = one folder with session.json, audio/ and transcript.jsonl."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path

from transcribe_anywhere.config import SEGMENT_SECONDS

# Track name -> speaker label shown in the transcript
TRACKS = {"mic": "Ich", "system": "Andere"}            # online meeting: microphone + system audio
INPERSON_TRACKS = {"mic": "Ich", "mic2": "Gast"}       # in-person meeting: two microphones
MODES = {"online": "Online-Meeting", "inperson": "Vor Ort (2 Mikrofone)"}

STATUS_LABELS = {
    "recording": "Aufnahme läuft",
    "recorded": "Wartet auf Transkription",
    "transcribing": "Wird transkribiert",
    "done": "Fertig",
    "interrupted": "Unterbrochen",
    "failed": "Fehler",
}


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\-]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return text[:40] or "meeting"


@dataclass
class Session:
    folder: Path
    id: str = ""
    title: str = ""
    started_at: str = ""
    ended_at: str = ""
    duration: float = 0.0
    speech_seconds: float = 0.0       # speech found by the VAD (both tracks)
    status: str = "recording"
    language: str = "de"
    mode: str = "online"              # "online" | "inperson" (see MODES)
    model: str = ""
    segment_seconds: int = SEGMENT_SECONDS
    markers: list[float] = field(default_factory=list)
    speaker_names: dict[str, str] = field(default_factory=dict)   # "Sprecher 1" -> "Anna"
    speakers: str = ""                # "" | "pending" | "done" | "failed" (speaker detection)
    error: str = ""

    @classmethod
    def create(cls, storage: Path, title: str = "", language: str = "de", mode: str = "online") -> "Session":
        now = datetime.now()
        title = title.strip() or f"Meeting {now:%d.%m.%Y %H:%M}"
        folder = storage / f"{now:%Y-%m-%d_%H%M%S}_{_slug(title)}"
        session = cls(
            folder=folder,
            id=uuid.uuid4().hex,
            title=title,
            started_at=now.isoformat(timespec="seconds"),
            language=language,
            mode=mode,
        )
        session.audio_dir.mkdir(parents=True, exist_ok=True)
        session.save()
        return session

    @classmethod
    def load(cls, folder: Path) -> "Session":
        data = json.loads((folder / "session.json").read_text("utf-8"))
        known = {f.name for f in fields(cls)} - {"folder"}
        return cls(folder=folder, **{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        data = asdict(self)
        data.pop("folder")
        tmp = self.folder / "session.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(self.folder / "session.json")   # atomic: never a half-written file

    @property
    def audio_dir(self) -> Path:
        return self.folder / "audio"

    @property
    def transcript_path(self) -> Path:
        return self.folder / "transcript.jsonl"

    @property
    def corrected_path(self) -> Path:
        return self.folder / "transcript.corrected.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.folder / "summary.md"

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def tracks(self) -> dict[str, str]:
        """Track name -> speaker label for this session's recording mode."""
        return INPERSON_TRACKS if self.mode == "inperson" else TRACKS

    def clock(self, seconds: float) -> str:
        """Wall-clock time of a point in the meeting, e.g. 14:03:27."""
        try:
            start = datetime.fromisoformat(self.started_at)
        except ValueError:
            return f"+{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"
        return (start + timedelta(seconds=seconds)).strftime("%H:%M:%S")

    def speaker_name(self, label: str) -> str:
        return self.speaker_names.get(label, label)

    def track_files(self, track: str) -> list[Path]:
        return sorted(self.audio_dir.glob(f"{track}_*.wav"))
