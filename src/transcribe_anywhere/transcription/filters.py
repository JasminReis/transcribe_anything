"""Remove typical Whisper hallucinations from the result."""

from __future__ import annotations

import re

from transcribe_anywhere.session.transcript import Segment

# Phrases Whisper learned from subtitled TV/YouTube and produces on silence or noise.
# Only matched in short segments, so a real sentence that mentions e.g. "Untertitel" survives.
_PHANTOM = re.compile(
    r"untertitel(ung)?\s+(im auftrag|des|der|von|by)"
    r"|amara\.org"
    r"|vielen dank f(ü|ue)r(s|'s)? zu(schauen|sehen|hören)"
    r"|danke f(ü|ue)r(s|'s)? zu(schauen|sehen|hören)"
    r"|thanks? (you )?for watching"
    r"|abonniert? (den|meinen|unseren) kanal"
    r"|copyright\b.*\b(wdr|swr|ndr|zdf|ard)\b",
    re.IGNORECASE,
)


def is_hallucination(text: str, no_speech_prob: float = 0.0, avg_logprob: float = 0.0) -> bool:
    t = text.strip()
    if not re.search(r"\w", t):
        return True
    if len(t.split()) <= 14 and _PHANTOM.search(t):
        return True
    # Whisper itself thinks there is no speech and is unsure about the words
    if no_speech_prob > 0.6 and avg_logprob < -0.8:
        return True
    return False


def collapse_repeats(segments: list[Segment], max_gap: float = 3.0) -> list[Segment]:
    """Drop immediate repetitions of the same sentence by the same speaker (looping)."""
    out: list[Segment] = []
    for seg in segments:
        prev = out[-1] if out else None
        if (prev and prev.speaker == seg.speaker and _norm(prev.text) == _norm(seg.text)
                and seg.start - prev.end <= max_gap):
            prev.end = max(prev.end, seg.end)
            continue
        out.append(seg)
    return out


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()
