"""Turn a recorded session (mic + system tracks) into one merged transcript.

Steps:  1. analyse   – find speech in every track (silence never reaches Whisper)
        2. transcribe – speech pieces cut at pauses, times mapped back to the meeting
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from transcribe_anywhere.session.session import TRACKS, Session
from transcribe_anywhere.session.transcript import Segment, write_segments
from transcribe_anywhere.transcription.engine import Cancelled, Transcriber
from transcribe_anywhere.transcription.filters import collapse_repeats
from transcribe_anywhere.transcription.segmenter import (
    SR,
    Chunk,
    TrackAudio,
    detect_speech,
    plan_chunks,
)


@dataclass
class Progress:
    stage: str                      # "load" | "analyse" | "transcribe" | "done"
    fraction: float = 0.0           # 0..1 within the stage
    audio_seconds: float = 0.0      # length of all tracks together
    speech_seconds: float = 0.0     # speech found in all tracks
    done_seconds: float = 0.0       # speech already transcribed
    elapsed: float = 0.0            # seconds spent in the current stage
    last_text: str = ""

    @property
    def speed(self) -> float:
        """Speech seconds per wall-clock second (×real time)."""
        return self.done_seconds / self.elapsed if self.elapsed > 1 and self.done_seconds else 0.0

    @property
    def eta(self) -> float | None:
        if self.stage != "transcribe" or self.speed <= 0:
            return None
        return (self.speech_seconds - self.done_seconds) / self.speed


def transcribe_chunk(
    chunk: Chunk, source, transcriber: Transcriber, speaker: str = "",
    should_cancel: Callable[[], bool] = lambda: False,
) -> Iterator[Segment]:
    """Transcribe one speech-only chunk; segment times are on the meeting timeline."""
    for seg in transcriber.transcribe(chunk.audio(source), 0.0, speaker, should_cancel, vad=False):
        seg.start = round(chunk.to_meeting_time(seg.start), 2)
        seg.end = round(chunk.to_meeting_time(seg.end, is_end=True), 2)
        yield seg


def transcribe_session(
    session: Session,
    transcriber: Transcriber,
    on_progress: Callable[[Progress], None] = lambda p: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[Segment]:
    tracks = {name: TrackAudio(session.track_files(name)) for name in TRACKS}
    total_samples = sum(t.total_samples for t in tracks.values())
    p = Progress("analyse", audio_seconds=total_samples / SR)
    on_progress(p)

    # 1. analyse ---------------------------------------------------------------
    t0, done_before = time.monotonic(), 0
    work = []
    for name, audio in tracks.items():
        def tick(samples, base=done_before):
            p.fraction = (base + samples) / max(total_samples, 1)
            p.elapsed = time.monotonic() - t0
            on_progress(p)

        regions = detect_speech(audio, tick, should_cancel)
        work += [(chunk, name) for chunk in plan_chunks(regions)]
        done_before += audio.total_samples
    work.sort(key=lambda item: item[0].start)       # meeting order across both tracks
    p.speech_seconds = sum(c.speech_seconds for c, _ in work)
    session.speech_seconds = round(p.speech_seconds, 1)
    session.save()

    # 2. transcribe --------------------------------------------------------------
    p.stage, p.fraction, p.elapsed = "transcribe", 0.0, 0.0
    on_progress(p)
    t0 = time.monotonic()
    segments: list[Segment] = []
    for chunk, name in work:
        if should_cancel():
            raise Cancelled()
        for seg in transcribe_chunk(chunk, tracks[name], transcriber, TRACKS[name], should_cancel):
            segments.append(seg)
            p.last_text = seg.text
            p.elapsed = time.monotonic() - t0
            on_progress(p)
        p.done_seconds += chunk.speech_seconds
        p.fraction = p.done_seconds / max(p.speech_seconds, 1e-9)
        p.elapsed = time.monotonic() - t0
        segments.sort(key=lambda s: s.start)
        write_segments(session.transcript_path, segments)   # partial results visible in the UI
        on_progress(p)

    segments = collapse_repeats(segments)
    write_segments(session.transcript_path, segments)
    p.stage, p.fraction = "done", 1.0
    on_progress(p)
    return segments
