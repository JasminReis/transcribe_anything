"""Find speech, cut it into pieces at pauses, and map times back to the meeting timeline.

Why: Whisper invents text ("Untertitel im Auftrag des ZDF …") when it is fed silence or noise.
So only speech is sent to Whisper, and pieces are cut only inside pauses, never inside words.

    track audio ──VAD──▶ speech regions ──group──▶ chunks (≤ 60 s speech each)
                                                    │  speech regions glued with short gaps
                                                    ▼
                                    Whisper ──▶ chunk times ──map──▶ meeting times
"""

from __future__ import annotations

import bisect
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SR = 16_000
WAV_HEADER = 44             # our writer always produces plain 44-byte PCM headers
VAD_WINDOW_S = 300          # analyse 5 minutes at a time (bounded memory for long meetings)
VAD_OVERLAP_S = 2           # windows overlap so words on a window border are never lost
GAP_S = 0.25                # silence inserted between glued speech regions
MAX_CHUNK_SPEECH_S = 60


# --------------------------------------------------------------------------- audio sources
class TrackAudio:
    """A track stored as several WAV files, read as one continuous signal.

    Reads raw PCM by file position (no memory maps → no Windows file locks), so it works on files
    with an unfinished header (crash) and on files that are still being written (live).
    """

    def __init__(self, files: list[Path] | Callable[[], list[Path]]):
        self._files_fn = files if callable(files) else (lambda f=list(files): f)
        self.refresh()

    def refresh(self) -> None:
        self.files = list(self._files_fn())
        self._starts = [0]
        for f in self.files:
            try:
                n = max(f.stat().st_size - WAV_HEADER, 0) // 2
            except OSError:
                n = 0
            self._starts.append(self._starts[-1] + n)

    @property
    def total_samples(self) -> int:
        return self._starts[-1]

    def read(self, start: int, end: int) -> np.ndarray:
        start, end = max(start, 0), min(end, self.total_samples)
        parts = []
        i = max(bisect.bisect_right(self._starts, start) - 1, 0)
        while start < end and i < len(self.files):
            local = start - self._starts[i]
            take = min(end, self._starts[i + 1]) - start
            if take > 0:
                parts.append(np.fromfile(self.files[i], dtype="<i2", count=take,
                                         offset=WAV_HEADER + 2 * local))
                start += take
            i += 1
        if not parts:
            return np.zeros(0, np.float32)
        return np.concatenate(parts).astype(np.float32) / 32768.0


class ArrayAudio:
    """Any decoded audio file (used by the CLI)."""

    def __init__(self, samples: np.ndarray):
        self.samples = samples.astype(np.float32)

    @classmethod
    def from_file(cls, path: Path) -> "ArrayAudio":
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path)) as w:
                    if w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2:
                        return cls(np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768.0)
            except wave.Error:
                pass
        from faster_whisper.audio import decode_audio

        return cls(decode_audio(str(path), sampling_rate=SR))

    @property
    def total_samples(self) -> int:
        return len(self.samples)

    def read(self, start: int, end: int) -> np.ndarray:
        return self.samples[max(start, 0) : min(end, len(self.samples))]


# --------------------------------------------------------------------------- speech detection
def vad_options():
    from faster_whisper.vad import VadOptions

    return VadOptions(
        threshold=0.5,
        min_speech_duration_ms=250,     # ignore clicks / keyboard
        min_silence_duration_ms=1000,   # a pause must be ≥ 1 s to separate regions
        speech_pad_ms=400,              # generous padding: never clip the first/last syllable
        max_speech_duration_s=30,       # very long monologues are split at short pauses
    )


def detect_speech(
    audio,
    on_progress: Callable[[int], None] = lambda samples_done: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[tuple[int, int]]:
    """Return speech regions as (start, end) sample positions on the track timeline."""
    from faster_whisper.vad import get_speech_timestamps

    opts = vad_options()
    total = audio.total_samples
    window, overlap = VAD_WINDOW_S * SR, VAD_OVERLAP_S * SR
    found: list[tuple[int, int]] = []
    for w0 in range(0, total, window):
        if should_cancel():
            from transcribe_anywhere.transcription.engine import Cancelled

            raise Cancelled()
        r0 = max(w0 - overlap, 0)
        chunk = audio.read(r0, min(w0 + window, total))
        found.extend((r0 + ts["start"], r0 + ts["end"]) for ts in get_speech_timestamps(chunk, opts))
        on_progress(min(w0 + window, total))
    return merge_overlapping(found)


def merge_overlapping(regions: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge regions that overlap (detected twice in the window overlap). Touching ones stay apart."""
    merged: list[tuple[int, int]] = []
    for s, e in sorted(regions):
        if merged and s < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


# --------------------------------------------------------------------------- chunks
@dataclass
class Chunk:
    regions: list[tuple[int, int]] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.regions[0][0] / SR

    @property
    def speech_seconds(self) -> float:
        return sum(e - s for s, e in self.regions) / SR

    def audio(self, source) -> np.ndarray:
        gap = np.zeros(int(GAP_S * SR), np.float32)
        parts = []
        for i, (s, e) in enumerate(self.regions):
            if i:
                parts.append(gap)
            parts.append(source.read(s, e))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)

    def to_meeting_time(self, t: float, is_end: bool = False) -> float:
        """Map a time inside the glued chunk audio back to the meeting timeline (seconds)."""
        pos = 0.0
        for i, (s, e) in enumerate(self.regions):
            length = (e - s) / SR
            if t <= pos + length or i == len(self.regions) - 1:
                return (s / SR) + min(max(t - pos, 0.0), length)
            pos += length
            if t < pos + GAP_S:           # inside an inserted gap
                return e / SR if is_end else self.regions[i + 1][0] / SR
            pos += GAP_S
        return self.regions[-1][1] / SR


def plan_chunks(regions: list[tuple[int, int]], max_speech_s: float = MAX_CHUNK_SPEECH_S) -> list[Chunk]:
    """Group consecutive speech regions; a new chunk starts only between regions (= in a pause)."""
    chunks: list[Chunk] = []
    current = Chunk()
    for region in regions:
        length = (region[1] - region[0]) / SR
        if current.regions and current.speech_seconds + length > max_speech_s:
            chunks.append(current)
            current = Chunk()
        current.regions.append(region)
    if current.regions:
        chunks.append(current)
    return chunks
