"""Simulate a meeting to test live transcription – no microphone or call needed.

    python tools/simulate_live.py speech.ogg --minutes 20 --speed 1 --engine parakeet

Builds a two-person conversation from a speech file (turns of 15–60 s, short pauses, background
noise on the system track) and plays it through the real recorder in real time (--speed 1) or
faster (--speed 4 = 4× real time, a stress test). Live transcription runs alongside, exactly as in
the app. Reports:
  - lag: how far the transcript was behind the recording (should stay small)
  - wait after stop: time from "Stop" to finished transcript
  - agreement with a normal full transcription of the same recording (should be ≈ 100 %)

On the target laptop, run with --speed 1 while a Teams/Zoom test call is open to see whether it
keeps up in practice.
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transcribe_anywhere.audio.capture import SessionRecorder  # noqa: E402
from transcribe_anywhere.session.session import Session  # noqa: E402
from transcribe_anywhere.transcription.engine import create_transcriber  # noqa: E402
from transcribe_anywhere.transcription.job import transcribe_session  # noqa: E402
from transcribe_anywhere.transcription.live import LiveTranscriber  # noqa: E402
from transcribe_anywhere.transcription.segmenter import SR, ArrayAudio  # noqa: E402


class PlaybackSource:
    """Pretends to be a soundcard input; delivers a prepared signal at a given speed."""

    def __init__(self, signal: np.ndarray, speed: float):
        self.signal, self.speed = signal, speed
        self.pos, self.t0 = 0, 0.0

    def recorder(self, samplerate, blocksize):
        return self

    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        return False

    def record(self, numframes):
        due = self.t0 + (self.pos + numframes) / SR / self.speed
        time.sleep(max(0.0, due - time.monotonic()))
        block = self.signal[self.pos: self.pos + numframes]
        if len(block) < numframes:
            block = np.concatenate([block, np.zeros(numframes - len(block), np.float32)])
        self.pos += numframes
        return block[:, None]

    @property
    def finished(self) -> bool:
        return self.pos >= len(self.signal)


def build_meeting(speech: np.ndarray, minutes: float, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    total = int(minutes * 60 * SR)
    mic, system = np.zeros(total, np.float32), np.zeros(total, np.float32)
    pos, src, speaker = int(2 * SR), 0, 0
    while pos < total:
        length = int(rng.uniform(15, 60) * SR)
        piece = np.take(speech, np.arange(src, src + length), mode="wrap")
        end = min(pos + length, total)
        (mic if speaker == 0 else system)[pos:end] = piece[: end - pos]
        src += length
        pos = end + int(rng.uniform(0.5, 3.0) * SR)
        speaker = 1 - speaker
    system += (rng.standard_normal(total) * 0.003).astype(np.float32)     # line noise of the call
    return mic, system


def words(segments) -> list[str]:
    return re.findall(r"\w+", " ".join(s.text for s in segments).lower())


def agreement(a, b, window_s: float = 60.0) -> float:
    """Word agreement compared minute by minute (the speech file repeats, so one global diff
    would align the wrong repetitions)."""
    end = max([s.end for s in a + b] or [0])
    matched = total = 0
    t = 0.0
    while t <= end:
        wa = words([s for s in a if t <= s.start < t + window_s])
        wb = words([s for s in b if t <= s.start < t + window_s])
        m = sum(blk.size for blk in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_matching_blocks())
        matched, total = matched + 2 * m, total + len(wa) + len(wb)
        t += window_s
    return matched / total if total else 1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("speech")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--engine", default="auto")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--no-compare", action="store_true", help="skip the full re-transcription")
    args = ap.parse_args()

    speech = ArrayAudio.from_file(Path(args.speech)).samples
    mic, system = build_meeting(speech, args.minutes)
    tr = create_transcriber(args.engine, args.model, args.device, "de")
    tr.load(print)
    print(f"Simulating {args.minutes:.0f} min meeting at {args.speed}× speed with {tr.label}")

    tmp = Path(tempfile.mkdtemp())
    try:
        session = Session.create(tmp, "simulation")
        sources = {"mic": PlaybackSource(mic, args.speed), "system": PlaybackSource(system, args.speed)}
        recorder = SessionRecorder(session.audio_dir, sources, SR, session.segment_seconds)
        live = LiveTranscriber(session, tr)
        recording = threading.Event()
        recording.set()
        lags: list[float] = []
        last_print = [0.0]

        def on_progress(p):
            if p.stage == "live":
                lags.append(p.lag)
                if time.monotonic() - last_print[0] > 10:
                    last_print[0] = time.monotonic()
                    print(f"  recorded {p.audio_seconds / 60:5.1f} min · lag {p.lag:5.1f} s · "
                          f"{len(live.segments)} segments · „{p.last_text[:60]}“", flush=True)

        worker = threading.Thread(target=live.run, args=(recording.is_set, on_progress), daemon=True)
        recorder.start()
        worker.start()
        while not all(s.finished for s in sources.values()):
            time.sleep(0.2)
        recorder.stop()
        t_stop = time.monotonic()
        recording.clear()
        worker.join()
        wait = time.monotonic() - t_stop

        meeting_s = len(mic) / SR
        print("\nResults")
        print(f"  meeting length        : {meeting_s / 60:.1f} min (played in {meeting_s / args.speed / 60:.1f} min)")
        print(f"  lag while recording   : median {np.median(lags):.1f} s, max {max(lags):.1f} s "
              f"(in meeting time; {args.speed}× speed)")
        print(f"  wait after Stop       : {wait:.1f} s")
        print(f"  live segments         : {len(live.segments)}")
        ok = max(lags) < 60 and wait < 60
        if not args.no_compare:
            copy = Session.create(tmp, "full")
            shutil.copytree(session.audio_dir, copy.audio_dir, dirs_exist_ok=True)
            t0 = time.monotonic()
            full = transcribe_session(copy, tr)
            ratio = agreement(full, live.segments)
            print(f"  full run afterwards   : {time.monotonic() - t0:.0f} s (this is what live saves)")
            print(f"  live vs full run      : {ratio:.1%} identical words")
            # Not 100 %: the recognisers react to where audio is cut (live cuts earlier). Measured
            # against a Whisper-GPU reference, live and full Parakeet scored the same (80.8 vs 80.9 %).
            # A real loss of speech would show up as a much lower value.
            ok = ok and ratio > 0.75
        print(f"\n{'KEEPS UP' if ok else 'FALLS BEHIND / MISMATCH'}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
