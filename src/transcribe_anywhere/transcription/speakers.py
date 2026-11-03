"""Tell the other participants apart: "Andere" becomes "Sprecher 1", "Sprecher 2" …

Runs offline after the transcript is finished, on the system-audio track only (the mic track
is always "Ich"). Uses sherpa-onnx speaker diarization: a pyannote model finds speaker
changes, a voice-fingerprint model (WeSpeaker ResNet34, trained on VoxCeleb – many languages)
groups the pieces by voice. Only the parts that were transcribed are analysed, so silence
costs nothing.
"""

from __future__ import annotations

import logging
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from transcribe_anywhere.config import models_dir
from transcribe_anywhere.session.session import TRACKS, Session
from transcribe_anywhere.session.transcript import Segment, read_segments, write_segments
from transcribe_anywhere.transcription.segmenter import SR, TrackAudio

log = logging.getLogger(__name__)

OTHER = TRACKS["system"]                 # "Andere"
PREFIX = "Sprecher "
_RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{_RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_URL = f"{_RELEASES}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx"
THRESHOLD = 0.5          # clustering distance; smaller = more speakers
PAD_S = 0.25             # audio kept around each transcribed piece
GAP_S = 0.3              # silence between pieces when they are joined
THREADS = 4


class Cancelled(Exception):
    pass


def is_other(label: str) -> bool:
    return label == OTHER or label.startswith(PREFIX)


def speakers_dir() -> Path:
    return models_dir() / "speakers"


def ensure_models(status: Callable[[str], None] = lambda _m: None) -> tuple[Path, Path]:
    """Download both models once (≈ 32 MB)."""
    target = speakers_dir()
    seg, emb = target / "segmentation.onnx", target / "embedding.onnx"
    if seg.exists() and emb.exists():
        return seg, emb
    target.mkdir(parents=True, exist_ok=True)
    status("Sprecher-Modelle werden heruntergeladen (≈ 32 MB, nur beim ersten Mal) …")
    if not seg.exists():
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "seg.tar.bz2"
            urllib.request.urlretrieve(SEGMENTATION_URL, archive)
            with tarfile.open(archive) as tar:
                member = next(m for m in tar.getmembers() if m.name.endswith("/model.onnx"))
                member.name = "model.onnx"            # flatten; never trust archive paths
                tar.extract(member, tmp, filter="data")
            (Path(tmp) / "model.onnx").replace(seg)
    if not emb.exists():
        part = emb.with_suffix(".part")
        urllib.request.urlretrieve(EMBEDDING_URL, part)
        part.replace(emb)
    return seg, emb


def _regions(segments: list[Segment], total: int) -> list[tuple[int, int]]:
    """Merged sample ranges around the given segments."""
    out: list[tuple[int, int]] = []
    for s in sorted(segments, key=lambda s: s.start):
        a = max(int((s.start - PAD_S) * SR), 0)
        b = min(int((s.end + PAD_S) * SR), total)
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def diarize(audio: np.ndarray, models: tuple[Path, Path],
            on_progress: Callable[[float], None] = lambda f: None,
            should_cancel: Callable[[], bool] = lambda: False) -> list[tuple[float, float, int]]:
    """Return (start, end, speaker index) in seconds of `audio`."""
    import sherpa_onnx as so

    seg, emb = models
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)), num_threads=THREADS),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(emb), num_threads=THREADS),
        clustering=so.FastClusteringConfig(num_clusters=-1, threshold=THRESHOLD),
        min_duration_on=0.3, min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("Sprecher-Modelle ungültig")
    sd = so.OfflineSpeakerDiarization(config)

    def callback(done: int, total: int) -> int:
        on_progress(done / total if total else 0.0)
        return 1 if should_cancel() else 0      # non-zero aborts

    result = sd.process(audio, callback=callback).sort_by_start_time()
    if should_cancel():
        raise Cancelled()
    return [(r.start, r.end, r.speaker) for r in result]


def label_segments(segments: list[Segment], turns: list[tuple[float, float, int]]) -> dict[tuple, str]:
    """Pick the speaker with the most overlap for every "other" segment (nearest turn if none).

    Speakers are numbered in order of first appearance. Returns {(start, end): label}.
    """
    labels: dict[tuple, str] = {}
    if not turns:
        return labels
    numbers: dict[int, int] = {}
    for s in sorted(segments, key=lambda s: s.start):
        overlap: dict[int, float] = {}
        for a, b, spk in turns:
            o = min(b, s.end) - max(a, s.start)
            if o > 0:
                overlap[spk] = overlap.get(spk, 0.0) + o
        if overlap:
            spk = max(overlap, key=overlap.get)
        else:
            mid = (s.start + s.end) / 2
            spk = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]
        numbers.setdefault(spk, len(numbers) + 1)
        labels[(s.start, s.end)] = f"{PREFIX}{numbers[spk]}"
    return labels


def assign_speakers(session: Session, on_progress: Callable[[float], None] = lambda f: None,
                    status: Callable[[str], None] = lambda _m: None,
                    should_cancel: Callable[[], bool] = lambda: False) -> int:
    """Relabel the other participants in the transcript (and the AI-corrected copy).

    Returns the number of different speakers found.
    """
    segments = read_segments(session.transcript_path)
    others = [s for s in segments if is_other(s.speaker)]
    if not others:
        return 0
    models = ensure_models(status)
    track = TrackAudio(session.track_files("system"))
    regions = _regions(others, track.total_samples)

    # Join the pieces (with short silences) and remember where each one came from.
    gap = np.zeros(int(GAP_S * SR), dtype=np.float32)
    pieces, offsets, pos = [], [], 0          # offsets: (joined start, meeting start, length) in samples
    for a, b in regions:
        if should_cancel():
            raise Cancelled()
        chunk = track.read(a, b).astype(np.float32)
        offsets.append((pos, a, len(chunk)))
        pieces += [chunk, gap]
        pos += len(chunk) + len(gap)
    audio = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)

    status("Sprecher werden erkannt …")
    turns = []
    for start, end, spk in diarize(audio, models, on_progress, should_cancel):
        s0, s1 = int(start * SR), int(end * SR)
        for j0, m0, n in offsets:                # split each turn back onto the meeting timeline
            lo, hi = max(s0, j0), min(s1, j0 + n)
            if hi > lo:
                turns.append(((m0 + lo - j0) / SR, (m0 + hi - j0) / SR, spk))

    labels = label_segments(others, turns)
    for path in (session.transcript_path, session.corrected_path):
        if not path.exists():
            continue
        segs = read_segments(path)
        for s in segs:
            if is_other(s.speaker):
                s.speaker = labels.get((s.start, s.end), s.speaker)
        write_segments(path, segs)
    return len(set(labels.values()))
