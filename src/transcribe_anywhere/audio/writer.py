"""Write a mono float stream into rotating 16-bit WAV files (mic_000.wav, mic_001.wav, …)."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np


class SegmentedWavWriter:
    def __init__(self, folder: Path, prefix: str, samplerate: int, segment_seconds: int):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.samplerate = samplerate
        self.segment_frames = samplerate * segment_seconds
        self.total_frames = 0
        self._index = 0
        self._in_segment = 0
        self._wav: wave.Wave_write | None = None
        self._lock = threading.Lock()
        self._closed = False

    def _open_next(self) -> None:
        path = self.folder / f"{self.prefix}_{self._index:03d}.wav"
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.samplerate)
        self._in_segment = 0

    def write(self, samples: np.ndarray) -> None:
        """samples: 1-D float array in [-1, 1]. Ignored after close()."""
        pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        with self._lock:
            if self._closed:
                return
            pos = 0
            while pos < len(pcm):
                if self._wav is None:
                    self._open_next()
                take = min(self.segment_frames - self._in_segment, len(pcm) - pos)
                self._wav.writeframes(pcm[pos : pos + take].tobytes())
                pos += take
                self._in_segment += take
                self.total_frames += take
                if self._in_segment >= self.segment_frames:
                    self._wav.close()
                    self._wav = None
                    self._index += 1

    def pad_to(self, frames: int) -> None:
        """Append silence until the stream is `frames` long (keeps tracks aligned)."""
        missing = frames - self.total_frames
        if missing > 0:
            self.write(np.zeros(missing, dtype=np.float32))

    def close(self) -> None:
        with self._lock:
            if self._wav is not None:
                self._wav.close()
                self._wav = None
            self._closed = True
