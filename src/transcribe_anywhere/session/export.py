"""Export and copy a transcript (TXT, Markdown, SRT, plain text, with an AI prompt).

Times are shown as wall-clock time (14:03:27) so you can see who said what when.
SRT keeps times relative to the start, because video players need that.
"""

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


def lines_with_times(session: Session, segments: list[Segment]) -> list[str]:
    """One line per segment: "[14:03:27] Anna: text"."""
    return [f"[{session.clock(s.start)}] {session.speaker_name(s.speaker)}: {s.text}" for s in segments]


def to_txt(session: Session, segments: list[Segment]) -> str:
    header = [session.title, fmt_date(session.started_at), ""]
    return "\n".join(header + lines_with_times(session, _with_markers(session, segments))) + "\n"


def to_markdown(session: Session, segments: list[Segment]) -> str:
    lines = [
        f"# {session.title}",
        "",
        f"*{fmt_date(session.started_at)} · {fmt_duration(session.duration)}*",
        "",
    ]
    for seg in _with_markers(session, segments):
        lines.append(f"**{session.clock(seg.start)} · {session.speaker_name(seg.speaker)}** {seg.text}  ")
    return "\n".join(lines) + "\n"


def to_srt(session: Session, segments: list[Segment]) -> str:
    blocks = []
    for i, seg in enumerate(segments, 1):
        who = session.speaker_name(seg.speaker)
        text = f"{who}: {seg.text}" if who else seg.text
        blocks.append(f"{i}\n{fmt_time(seg.start, True)} --> {fmt_time(seg.end, True)}\n{text}\n")
    return "\n".join(blocks)


def copy_with_times(session: Session, segments: list[Segment]) -> str:
    return "\n".join(lines_with_times(session, segments)) + "\n"


def copy_plain(session: Session, segments: list[Segment]) -> str:
    """Speaker turns as paragraphs – best for pasting into mails, docs or chat tools."""
    turns: list[tuple[str, list[str]]] = []
    for s in segments:
        who = session.speaker_name(s.speaker)
        if turns and turns[-1][0] == who:
            turns[-1][1].append(s.text)
        else:
            turns.append((who, [s.text]))
    return "\n\n".join(f"{who}: {' '.join(texts)}" for who, texts in turns) + "\n"


def transcript_block(session: Session, segments: list[Segment]) -> str:
    """Transcript with a short header, as handed to an AI (copied or sent to Claude/OpenAI)."""
    head = f"Besprechung: {session.title}\nDatum: {fmt_date(session.started_at)}"
    if session.duration:
        head += f" · Dauer: {fmt_duration(session.duration)}"
    return f"{head}\n\n" + copy_with_times(session, segments)


def copy_with_prompt(prompt: str, session: Session, segments: list[Segment]) -> str:
    """Prompt + transcript, ready to paste into ChatGPT, Claude or any other chat AI."""
    return f"{prompt.strip()}\n\n---\n\n{transcript_block(session, segments)}"


EXPORTERS = {"txt": to_txt, "md": to_markdown, "srt": to_srt}
