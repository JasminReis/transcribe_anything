"""Record microphone and system audio in parallel, one thread per track."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np

from transcribe_anywhere.audio.writer import SegmentedWavWriter

BLOCK_SECONDS = 0.1


def _init_thread_com() -> None:
    """WASAPI needs COM initialised on every thread that touches audio."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED


class TrackRecorder(threading.Thread):
    def __init__(self, source, writer: SegmentedWavWriter, samplerate: int, t0: float):
        super().__init__(daemon=True, name=f"capture-{writer.prefix}")
        self.source = source
        self.writer = writer
        self.samplerate = samplerate
        self.t0 = t0                      # shared start time of all tracks
        self.level = 0.0                  # RMS of the last block, read by the UI
        self.error: Exception | None = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        _init_thread_com()
        frames = int(self.samplerate * BLOCK_SECONDS)
        try:
            with self.source.recorder(samplerate=self.samplerate, blocksize=frames) as rec:
                while not self._stop_event.is_set():
                    data = rec.record(numframes=frames)
                    mono = data.mean(axis=1) if data.ndim == 2 else data
                    # Windows loopback delivers nothing while no sound plays.
                    # Fill that gap with silence so all tracks share one timeline.
                    expected = int((time.monotonic() - self.t0) * self.samplerate)
                    gap = expected - self.writer.total_frames - len(mono)
                    if gap > self.samplerate // 2:
                        self.writer.write(np.zeros(gap, dtype=np.float32))
                    self.writer.write(mono.astype(np.float32))
                    self.level = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0
        except Exception as exc:  # surfaced to the UI via .error
            self.error = exc

    def stop(self) -> None:
        self._stop_event.set()


class SessionRecorder:
    """Records all tracks of one session into `audio_dir`."""

    def __init__(self, audio_dir: Path, sources: dict[str, object], samplerate: int, segment_seconds: int):
        self.samplerate = samplerate
        self.t0 = 0.0
        self.writers = {
            name: SegmentedWavWriter(audio_dir, name, samplerate, segment_seconds) for name in sources
        }
        self._sources = sources
        self.tracks: dict[str, TrackRecorder] = {}

    def start(self) -> None:
        self.t0 = time.monotonic()
        for name, source in self._sources.items():
            track = TrackRecorder(source, self.writers[name], self.samplerate, self.t0)
            self.tracks[name] = track
            track.start()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0 if self.t0 else 0.0

    def levels(self) -> dict[str, float]:
        return {name: t.level for name, t in self.tracks.items()}

    def errors(self) -> dict[str, Exception]:
        return {name: t.error for name, t in self.tracks.items() if t.error}

    def stop(self) -> float:
        """Stop all tracks, pad them to equal length, return the duration in seconds."""
        duration = self.elapsed
        for track in self.tracks.values():
            track.stop()
        for track in self.tracks.values():
            track.join(timeout=2.0)   # a silent loopback may block in record(); don't wait forever
        end_frames = int(duration * self.samplerate)
        for writer in self.writers.values():
            writer.pad_to(end_frames)
            writer.close()
        return duration
