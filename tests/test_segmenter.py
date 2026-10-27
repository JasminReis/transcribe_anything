import numpy as np
import pytest

from transcribe_anywhere.audio.writer import SegmentedWavWriter
from transcribe_anywhere.session.transcript import Segment
from transcribe_anywhere.transcription.filters import collapse_repeats, is_hallucination
from transcribe_anywhere.transcription.segmenter import (
    GAP_S,
    SR,
    ArrayAudio,
    Chunk,
    TrackAudio,
    detect_speech,
    merge_overlapping,
    plan_chunks,
)


def test_track_reads_continuously_across_files(tmp_path):
    signal = (np.arange(SR * 5) % 1000 / 1000 - 0.5).astype(np.float32)
    w = SegmentedWavWriter(tmp_path, "mic", SR, segment_seconds=2)   # 3 files: 2 s + 2 s + 1 s
    w.write(signal)
    w.close()
    track = TrackAudio(sorted(tmp_path.glob("mic_*.wav")))
    assert track.total_samples == len(signal)
    part = track.read(SR * 2 - 100, SR * 2 + 100)                   # spans the file border
    assert np.allclose(part, signal[SR * 2 - 100 : SR * 2 + 100], atol=2 / 32768)


def test_track_survives_unfinished_header(tmp_path):
    w = SegmentedWavWriter(tmp_path, "mic", SR, segment_seconds=60)
    w.write(np.full(SR, 0.25, np.float32))
    # simulate a crash: data is on disk (flushed), header never finalised
    track = TrackAudio(sorted(tmp_path.glob("mic_*.wav")))
    assert track.total_samples == SR


def test_merge_keeps_touching_regions_apart():
    assert merge_overlapping([(10, 20), (15, 30), (30, 40), (50, 60)]) == [(10, 30), (30, 40), (50, 60)]


def test_chunks_split_only_between_regions():
    regions = [(i * SR * 20, i * SR * 20 + SR * 15) for i in range(10)]   # 10 × 15 s speech
    chunks = plan_chunks(regions, max_speech_s=60)
    assert [len(c.regions) for c in chunks] == [4, 4, 2]
    assert sum(c.speech_seconds for c in chunks) == pytest.approx(150)
    assert [r for c in chunks for r in c.regions] == regions             # nothing lost or reordered


def test_chunk_time_mapping():
    chunk = Chunk([(SR * 100, SR * 110), (SR * 200, SR * 205)])         # 10 s, gap, 5 s
    assert chunk.to_meeting_time(0) == 100
    assert chunk.to_meeting_time(9.5) == 109.5
    assert chunk.to_meeting_time(10 + GAP_S / 2) == 200                 # start inside gap → next region
    assert chunk.to_meeting_time(10 + GAP_S / 2, is_end=True) == 110    # end inside gap → region end
    assert chunk.to_meeting_time(10 + GAP_S + 2) == 202
    assert chunk.to_meeting_time(99) == 205                             # clamped
    audio = chunk.audio(ArrayAudio(np.ones(SR * 300, np.float32)))
    assert len(audio) == SR * 15 + int(GAP_S * SR)


def test_silence_and_noise_contain_no_speech():
    rng = np.random.default_rng(0)
    quiet = np.zeros(SR * 30, np.float32)
    hiss = (rng.standard_normal(SR * 30) * 0.01).astype(np.float32)
    hum = (0.05 * np.sin(2 * np.pi * 50 * np.arange(SR * 30) / SR)).astype(np.float32)
    for signal in (quiet, hiss, hum):
        assert detect_speech(ArrayAudio(signal)) == []


@pytest.mark.parametrize("text", [
    "Untertitel im Auftrag des ZDF für funk, 2017",
    "Untertitel der Amara.org-Community",
    "Vielen Dank fürs Zuschauen!",
    "Thanks for watching.",
    "...",
])
def test_phantom_phrases_are_dropped(text):
    assert is_hallucination(text)


@pytest.mark.parametrize("text", [
    "Vielen Dank, dann machen wir so weiter.",
    "Die Untertitel im Video müssen wir noch prüfen, das war ein Thema beim letzten Kunden und auch heute.",
])
def test_real_sentences_are_kept(text):
    assert not is_hallucination(text)


def test_collapse_repeats():
    segs = [Segment(0, 2, "Okay.", "Ich"), Segment(2.5, 4, "Okay.", "Ich"), Segment(5, 6, "Okay.", "Andere")]
    assert [s.speaker for s in collapse_repeats(segs)] == ["Ich", "Andere"]
