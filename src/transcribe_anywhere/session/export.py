"""Export a transcript to TXT, Markdown or SRT."""

from __future__ import annotations

from datetime import datetime

from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.transcript import Segment


def fmt_time(seconds: float, srt: bool = False) -> str:
    ms = int(round(seconds * 1000))
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}" if srt else f"{h:02d}:{m:02d}:{s:02d}"


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso


def fmt_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60}:{minutes % 60:02d} h" if minutes >= 60 else f"{minutes} min"


def _with_markers(session: Session, segments: list[Segment]) -> list[Segment]:
    marks = [Segment(t, t, "Marker", "⚑") for t in session.markers]
    return sorted(segments + marks, key=lambda s: s.start)


def to_txt(session: Session, segments: list[Segment]) -> str:
    lines = [session.title, fmt_date(session.started_at), ""]
    for seg in _with_markers(session, segments):
        lines.append(f"[{fmt_time(seg.start)}] {seg.speaker}: {seg.text}")
    return "\n".join(lines) + "\n"


def to_markdown(session: Session, segments: list[Segment]) -> str:
    lines = [
        f"# {session.title}",
        "",
        f"*{fmt_date(session.started_at)} · {fmt_duration(session.duration)}*",
        "",
    ]
    for seg in _with_markers(session, segments):
        lines.append(f"**{fmt_time(seg.start)} · {seg.speaker}** {seg.text}  ")
    return "\n".join(lines) + "\n"


def to_srt(session: Session, segments: list[Segment]) -> str:
    blocks = []
    for i, seg in enumerate(segments, 1):
        text = f"{seg.speaker}: {seg.text}" if seg.speaker else seg.text
        blocks.append(f"{i}\n{fmt_time(seg.start, True)} --> {fmt_time(seg.end, True)}\n{text}\n")
    return "\n".join(blocks)


EXPORTERS = {"txt": to_txt, "md": to_markdown, "srt": to_srt}
