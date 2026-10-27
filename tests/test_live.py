"""Live transcription on a simulated growing recording (fake VAD + fake engine, no models)."""

import numpy as np

from transcribe_anywhere.audio.writer import SegmentedWavWriter
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.transcript import Segment, read_segments
from transcribe_anywhere.transcription.live import LiveTranscriber
from transcribe_anywhere.transcription.segmenter import SR

# speech bursts on the mic track (start s, length s); file size 4 s → several cross file borders
BURSTS = [(1.0, 2.0), (3.5, 1.5), (7.8, 0.9), (11.0, 5.5), (19.0, 0.6), (22.2, 3.0)]
TOTAL_S = 27.0


def energy_vad(samples):
    """Stand-in for Silero: regions where the signal is loud, padded by 0.1 s."""
    loud = np.abs(samples) > 0.1
    regions, start = [], None
    for i in range(0, len(samples), 160):                    # 10 ms steps
        on = bool(loud[i:i + 160].any())
        if on and start is None:
            start = i
        if not on and start is not None:
            regions.append((max(start - 1600, 0), min(i + 1600, len(samples))))
            start = None
    if start is not None:
        regions.append((max(start - 1600, 0), len(samples)))
    merged = []
    for s, e in regions:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


class FakeEngine:
    """Returns one segment per loud run inside the chunk, text = its length."""
    engine, label = "fake", "fake"

    def transcribe(self, audio, offset=0.0, speaker="", should_cancel=None, vad=True):
        for s, e in energy_vad(audio):
            run = np.flatnonzero(np.abs(audio[s:e]) > 0.1)
            a, b = (s + run[0]) / SR, (s + run[-1] + 1) / SR
            yield Segment(a, b, f"{b - a:.1f}s", speaker)


class FakeClock:
    t = 0.0

    def __call__(self):
        return self.t


def _signal():
    sig = np.zeros(int(TOTAL_S * SR), np.float32)
    for start, length in BURSTS:
        sig[int(start * SR): int((start + length) * SR)] = 0.5
    return sig


def test_live_transcribes_every_burst_exactly_once(tmp_path):
    session = Session.create(tmp_path, "live")
    sig, silent = _signal(), np.zeros(int(TOTAL_S * SR), np.float32)
    writers = {n: SegmentedWavWriter(session.audio_dir, n, SR, 4) for n in ("mic", "system")}
    clock = FakeClock()
    live = LiveTranscriber(session, FakeEngine(), min_batch_s=1.0, max_wait_s=2.0, vad=energy_vad, clock=clock)

    pos, step = 0, int(0.7 * SR)              # audio arrives in odd-sized pieces
    early_text = None
    while pos < len(sig):
        for name, data in (("mic", sig), ("system", silent)):
            writers[name].write(data[pos: pos + step])
        pos += step
        clock.t += 0.7
        live.step()
        if early_text is None and pos > 20 * SR:
            early_text = len(live.segments)
    for w in writers.values():
        w.close()
    live.step(final=True)
    while live.step(final=True):
        pass

    got = sorted((round(s.start, 2), s.text) for s in live.segments)
    assert got == [(start, f"{length:.1f}s") for start, length in BURSTS]   # all, once, right time
    assert all(s.speaker == "Ich" for s in live.segments)
    assert early_text and early_text >= 4          # text appeared while "recording", not only at the end
    assert read_segments(session.transcript_path) == live.segments
    assert live.lag == 0


def test_live_skips_long_silence_cheaply(tmp_path):
    session = Session.create(tmp_path, "quiet")
    for n in ("mic", "system"):
        w = SegmentedWavWriter(session.audio_dir, n, SR, 60)
        w.write(np.zeros(SR * 300, np.float32))
        w.close()
    calls = []

    def counting_vad(samples):
        calls.append(len(samples))
        return []

    live = LiveTranscriber(session, FakeEngine(), vad=counting_vad)
    while live.step(final=True):
        pass
    assert live.segments == []
    assert max(calls) <= 120 * SR                  # never analyses more than 2 minutes at once
    assert sum(calls) <= 1.05 * 2 * 300 * SR       # each second analysed about once (1.5 s overlap per window)
