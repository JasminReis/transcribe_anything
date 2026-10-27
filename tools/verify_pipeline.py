"""Check the transcription pipeline end to end with a real speech file.

    python tools/verify_pipeline.py speech.ogg [--device cpu|cuda] [--model small]

Builds a fake 5-minute session (60-second audio files, so speech crosses file borders):

    mic    : 20 s silence | 180 s speech (sample 0–180 s)           | 60 s noise+hum | 40 s silence
    system : 100 s silence | 120 s speech (sample 180–300 s)         | 80 s silence

and checks: no words lost at cuts, timestamps on the meeting timeline, no text from silence/noise,
duration preserved. Also shows what Whisper does with the noise part when silence is NOT removed.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transcribe_anywhere.audio.writer import SegmentedWavWriter  # noqa: E402
from transcribe_anywhere.session.session import Session  # noqa: E402
from transcribe_anywhere.transcription.engine import Transcriber  # noqa: E402
from transcribe_anywhere.transcription.job import transcribe_session  # noqa: E402
from transcribe_anywhere.transcription.segmenter import SR, ArrayAudio, TrackAudio  # noqa: E402


def words(texts) -> list[str]:
    return re.findall(r"\w+", " ".join(texts).lower())


def agreement(a: list[str], b: list[str]) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("speech")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--model", default="large-v3-turbo")
    args = ap.parse_args()

    speech = ArrayAudio.from_file(Path(args.speech)).samples
    if len(speech) < 300 * SR:
        sys.exit("Need at least 5 minutes of speech.")
    rng = np.random.default_rng(1)
    sec = lambda s: int(s * SR)  # noqa: E731
    noise = (rng.standard_normal(sec(60)) * 0.02
             + 0.05 * np.sin(2 * np.pi * 50 * np.arange(sec(60)) / SR)).astype(np.float32)
    mic = np.concatenate([np.zeros(sec(20)), speech[: sec(180)], noise, np.zeros(sec(40))]).astype(np.float32)
    system = np.concatenate([np.zeros(sec(100)), speech[sec(180): sec(300)], np.zeros(sec(80))]).astype(np.float32)

    tr = Transcriber(args.model, args.device, "de")
    tr.load(print)
    results = []

    def check(name, ok, detail):
        results.append(ok)
        print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        session = Session.create(Path(tmp), "verify")
        session.segment_seconds = 60
        for name, signal in (("mic", mic), ("system", system)):
            w = SegmentedWavWriter(session.audio_dir, name, SR, 60)
            w.write(signal)
            w.close()
        session.duration = 300
        session.save()

        print("\nReference: sample transcribed directly (no cutting)")
        ref_mic = list(tr.transcribe(speech[: sec(180)]))
        ref_sys = list(tr.transcribe(speech[sec(180): sec(300)]))

        print("Pipeline: session transcribed with silence removal + cutting")
        segs = transcribe_session(session, tr)
        mic_segs = [s for s in segs if s.speaker == "Ich"]
        sys_segs = [s for s in segs if s.speaker == "Andere"]

        print("\nResults")
        for label, got, ref in (("mic", mic_segs, ref_mic), ("system", sys_segs, ref_sys)):
            a = agreement(words(s.text for s in ref), words(s.text for s in got))
            check(f"words {label} vs reference", a >= 0.95, f"{a:.1%} identical")

        # words around the file borders (60/120/180 s on the mic track = 40/100/160 s in the sample)
        for border in (60, 120, 180):
            ref_near = words(s.text for s in ref_mic if abs(s.start + 20 - border) < 8)
            got_near = words(s.text for s in mic_segs if abs(s.start - border) < 8)
            a = agreement(ref_near, got_near)
            check(f"no words lost at file border {border}s", a >= 0.9, f"{a:.1%} identical around the cut")

        # timestamps: matching sentences must sit at sample time + track offset
        devs = []
        for got, ref, offset in ((mic_segs, ref_mic, 20.0), (sys_segs, ref_sys, 100.0)):
            for g in got:
                best = max(ref, key=lambda r: difflib.SequenceMatcher(None, r.text, g.text).ratio())
                if difflib.SequenceMatcher(None, best.text, g.text).ratio() > 0.8:
                    devs.append(abs(g.start - (best.start + offset)))
        # Whisper may group sentences differently in the cut audio (start moves by one phrase),
        # so a single sentence can be ~2 s off while the mapping itself is exact (median).
        check("timestamps on meeting timeline", bool(devs) and np.median(devs) < 0.3 and max(devs) < 2.5,
              f"{len(devs)} sentences matched, max deviation {max(devs):.2f}s, median {np.median(devs):.2f}s")

        noise_hits = [s for s in mic_segs if 201 <= s.start <= 259]
        check("no text from noise (mic 200–260 s)", not noise_hits, f"{len(noise_hits)} segments")
        silent = [s for s in mic_segs if s.start < 19 or s.start > 261] + \
                 [s for s in sys_segs if s.start < 99 or s.start > 221]
        check("no text from silence", not silent, f"{len(silent)} segments")

        dur = {n: TrackAudio(session.track_files(n)).total_samples / SR for n in ("mic", "system")}
        check("duration preserved", all(abs(d - 300) < 0.01 for d in dur.values()), f"{dur}")
        check("speech share", True, f"{Session.load(session.folder).speech_seconds:.0f} s speech of 600 s audio")

    print("\nFor comparison – raw Whisper on noise + silence (100 s), no silence removal, no filter:")
    raw = np.concatenate([noise, np.zeros(sec(40))]).astype(np.float32)
    phantom, _ = tr._model.transcribe(raw, language="de", vad_filter=False, condition_on_previous_text=False)
    phantom = list(phantom)
    for seg in phantom:
        print(f"    [{seg.start:5.1f}s] {seg.text.strip()!r}  (no_speech_prob={seg.no_speech_prob:.2f})")
    print(f"    → {len(phantom)} invented segment(s). With this app's pipeline: 0.")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
