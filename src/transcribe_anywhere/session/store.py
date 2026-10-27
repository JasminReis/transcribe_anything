"""The session library: list sessions and recover after a crash."""

from __future__ import annotations

from pathlib import Path

from transcribe_anywhere.session.session import Session


def list_sessions(storage: Path) -> list[Session]:
    sessions = []
    if storage.exists():
        for meta in storage.glob("*/session.json"):
            try:
                sessions.append(Session.load(meta.parent))
            except (OSError, ValueError, TypeError):
                continue
    return sorted(sessions, key=lambda s: s.started_at, reverse=True)


def recover_interrupted(storage: Path) -> list[Session]:
    """Call once at startup: anything still 'recording'/'transcribing' was cut off by a crash."""
    recovered = []
    for session in list_sessions(storage):
        if session.status in ("recording", "transcribing"):
            if session.status == "recording" and not session.duration:
                files = session.track_files("mic") or session.track_files("system")
                session.duration = _wav_duration(files)
            session.status = "interrupted"
            session.save()
            recovered.append(session)
    return recovered


def _wav_duration(files: list[Path]) -> float:
    import wave

    total = 0.0
    for path in files:
        try:
            with wave.open(str(path)) as w:
                total += w.getnframes() / w.getframerate()
        except (OSError, EOFError, wave.Error):
            # Header of the last file is not finalised after a crash; estimate from size.
            total += max(path.stat().st_size - 44, 0) / (2 * 16_000)
    return total
