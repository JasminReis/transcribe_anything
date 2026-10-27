"""Live transcription: follow the growing track files while the meeting is being recorded.

Every second, per track:
  1. scan   – run the VAD over the audio that arrived since the last scan
  2. collect – speech regions that are clearly finished (followed by ≥ 1.5 s of audio) wait in
              `pending`; a region still running at the end is scanned again next time
  3. batch  – once enough speech is pending (or it waited long enough), it is cut into chunks
              exactly like the offline pipeline and transcribed

After Stop, everything left is processed with `final=True`, so the transcript is ready seconds
to minutes after the meeting instead of after a full re-run. The audio files on disk stay the
source of truth: if live transcription falls behind or crashes, nothing is lost.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from transcribe_anywhere.session.session import TRACKS, Session
from transcribe_anywhere.session.transcript import Segment, write_segments
from transcribe_anywhere.transcription.engine import Cancelled
from transcribe_anywhere.transcription.filters import collapse_repeats
from transcribe_anywhere.transcription.job import Progress, transcribe_chunk
from transcribe_anywhere.transcription.segmenter import SR, TrackAudio, plan_chunks, vad_options

SAFETY_S = 1.5          # audio this close to the end may be speech still in progress
MAX_SCAN_S = 120        # analyse at most this much new audio per step (when catching up)


def silero_regions(samples) -> list[tuple[int, int]]:
    from faster_whisper.vad import get_speech_timestamps

    return [(ts["start"], ts["end"]) for ts in get_speech_timestamps(samples, vad_options())]


@dataclass
class TrackState:
    name: str
    speaker: str
    audio: TrackAudio
    scan_from: int = 0                                      # sample position of the next scan
    pending: list[tuple[int, int]] = field(default_factory=list)
    pending_since: float = 0.0

    @property
    def covered(self) -> int:
        """Everything before this sample position is transcribed."""
        return self.pending[0][0] if self.pending else self.scan_from


class LiveTranscriber:
    def __init__(self, session: Session, transcriber, min_batch_s: float | None = None,
                 max_wait_s: float | None = None, vad: Callable = silero_regions,
                 clock: Callable[[], float] = time.monotonic):
        parakeet = getattr(transcriber, "engine", "") == "parakeet"
        # Whisper always computes 30-s windows, so feed it bigger batches; Parakeet is cheap per call.
        self.min_batch_s = min_batch_s if min_batch_s is not None else (3.0 if parakeet else 20.0)
        self.max_wait_s = max_wait_s if max_wait_s is not None else (3.0 if parakeet else 10.0)
        self.session = session
        self.transcriber = transcriber
        self.vad = vad
        self.clock = clock
        self.tracks = [TrackState(name, speaker, TrackAudio(lambda n=name: session.track_files(n)))
                       for name, speaker in TRACKS.items()]
        self.segments: list[Segment] = []
        self.speech_seconds = 0.0
        self.last_text = ""

    # --- one step ---------------------------------------------------------------
    def _scan(self, st: TrackState, final: bool) -> bool:
        """Find finished speech regions in new audio. Returns True if more audio is waiting."""
        st.audio.refresh()
        total = st.audio.total_samples
        end = min(total, st.scan_from + MAX_SCAN_S * SR)
        capped = end < total
        horizon = end if (final and not capped) else end - int(SAFETY_S * SR)
        if horizon - st.scan_from < SR // 4:
            return capped
        regions = [(st.scan_from + s, st.scan_from + e) for s, e in self.vad(st.audio.read(st.scan_from, end))]
        complete = [r for r in regions if r[1] <= horizon]
        running = [r for r in regions if r[1] > horizon]
        if complete and not st.pending:
            st.pending_since = self.clock()
        st.pending += complete
        st.scan_from = running[0][0] if running else horizon
        return capped

    def _flush(self, st: TrackState, final: bool, should_cancel) -> bool:
        if not st.pending:
            return False
        speech = sum(e - s for s, e in st.pending) / SR
        waited = self.clock() - st.pending_since
        if not final and speech < self.min_batch_s and waited < self.max_wait_s:
            return False
        for chunk in plan_chunks(st.pending):
            for seg in transcribe_chunk(chunk, st.audio, self.transcriber, st.speaker, should_cancel):
                self.segments.append(seg)
                self.last_text = seg.text
        self.speech_seconds += speech
        st.pending = []
        self.segments.sort(key=lambda s: s.start)
        write_segments(self.session.transcript_path, self.segments)
        return True

    def step(self, final: bool = False, should_cancel: Callable[[], bool] = lambda: False) -> bool:
        """Process what is ready. Returns True if work was done (call again soon)."""
        did = False
        for st in self.tracks:
            more = self._scan(st, final)
            did = self._flush(st, final, should_cancel) or did or more
        return did

    # --- status -----------------------------------------------------------------
    @property
    def recorded_seconds(self) -> float:
        return max(st.audio.total_samples for st in self.tracks) / SR

    @property
    def covered_seconds(self) -> float:
        return min(st.covered for st in self.tracks) / SR

    @property
    def lag(self) -> float:
        return max(0.0, self.recorded_seconds - self.covered_seconds)

    def progress(self, stage: str, fraction: float = 0.0) -> Progress:
        return Progress(stage, fraction, audio_seconds=self.recorded_seconds,
                        speech_seconds=self.speech_seconds, done_seconds=self.covered_seconds,
                        last_text=self.last_text, lag=self.lag,
                        engine=getattr(self.transcriber, "label", ""))

    # --- main loop --------------------------------------------------------------
    def run(self, recording: Callable[[], bool], on_progress: Callable[[Progress], None] = lambda p: None,
            should_cancel: Callable[[], bool] = lambda: False, poll_s: float = 1.0) -> list[Segment]:
        while recording():
            if should_cancel():
                raise Cancelled()
            did = self.step(should_cancel=should_cancel)
            on_progress(self.progress("live"))
            if not did:
                waited = 0.0
                while waited < poll_s and recording():
                    time.sleep(0.1)
                    waited += 0.1

        # Stopped: transcribe the rest
        start_lag = max(self.lag, 1e-9)
        t0 = time.monotonic()
        while True:
            if should_cancel():
                raise Cancelled()
            p = self.progress("finish", min(1.0, 1 - self.lag / start_lag))
            p.elapsed = time.monotonic() - t0
            on_progress(p)
            if not self.step(final=True, should_cancel=should_cancel):
                break
        self.segments = collapse_repeats(self.segments)
        write_segments(self.session.transcript_path, self.segments)
        on_progress(self.progress("done", 1.0))
        return self.segments
