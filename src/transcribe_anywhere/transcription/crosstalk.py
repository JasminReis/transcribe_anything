"""In-person meetings: keep each person's voice on their own microphone.

With two microphones in one room, each microphone also hears the other person ("crosstalk").
Without help, every sentence would be transcribed twice. For every 20 ms we compare the
loudness of both microphones: where the other microphone is clearly louder, this microphone
only hears the other person, so it is muted there. Short holds and fades keep word endings
intact. The WAV files on disk stay untouched; this only changes what the recogniser hears.
"""

from __future__ import annotations

import numpy as np

from transcribe_anywhere.session.session import Session
from transcribe_anywhere.transcription.segmenter import SR, TrackAudio

FRAME = SR // 50          # 20 ms
SMOOTH_FRAMES = 3         # loudness is compared over ~60 ms
MARGIN_DB = 4.0           # the other mic must be this much louder to count as "their" voice
# Tested on simulated rooms: mics close to each person (crosstalk -12 dB) → no duplicates;
# mics close together (-6 dB) or two different mic models → occasional duplicate or wrong speaker.
HOLD_S = 0.25             # keep this much audio around own speech (word starts/endings)


def gate(own: np.ndarray, other: np.ndarray, margin_db: float = MARGIN_DB, hold_s: float = HOLD_S) -> np.ndarray:
    """Return `own` with the parts muted where `other` is clearly louder (= crosstalk)."""
    n = len(own)
    if n == 0:
        return own
    other = other[:n] if len(other) >= n else np.pad(other, (0, n - len(other)))
    frames = -(-n // FRAME)
    pad = frames * FRAME - n
    # Loudness per 20 ms, smoothed over ~60 ms: the two mics hear a voice a few ms apart.
    smooth = np.ones(SMOOTH_FRAMES) / SMOOTH_FRAMES
    p_own = np.mean(np.pad(own, (0, pad)).reshape(frames, FRAME) ** 2, axis=1)
    p_other = np.mean(np.pad(other, (0, pad)).reshape(frames, FRAME) ** 2, axis=1)
    p_own, p_other = np.convolve(p_own, smooth, mode="same"), np.convolve(p_other, smooth, mode="same")
    diff = 10 * np.log10((p_other + 1e-12) / (p_own + 1e-12))
    crosstalk = diff > margin_db               # the other mic is clearly louder: their voice
    own_voice = diff < -margin_db              # this mic is clearly louder: our own voice
    hold = max(int(hold_s * SR / FRAME), 0)
    if hold:                                   # protect our own word starts/endings (not silence!)
        own_voice = np.convolve(own_voice.astype(float), np.ones(2 * hold + 1), mode="same") > 0
    keep = ~(crosstalk & ~own_voice)           # silence and both-talking-at-once stay untouched
    gain = np.repeat(keep.astype(np.float32), FRAME)[:n]
    fade = np.ones(FRAME, dtype=np.float32) / FRAME   # 20 ms fade instead of hard cuts
    gain = np.convolve(gain, fade, mode="same")
    return (own * gain).astype(np.float32)


class GatedAudio:
    """A track that reads like TrackAudio, but with the other microphone's crosstalk removed."""

    def __init__(self, own: TrackAudio, other: TrackAudio):
        self.own, self.other = own, other

    def refresh(self) -> None:
        self.own.refresh()
        self.other.refresh()

    @property
    def total_samples(self) -> int:
        return self.own.total_samples

    def read(self, start: int, end: int) -> np.ndarray:
        # Read a little extra on both sides so the hold/fade is correct at the edges.
        margin = int(HOLD_S * SR) + FRAME
        a, b = max(start - margin, 0), min(end + margin, self.own.total_samples)
        own = self.own.read(a, b)
        gated = gate(own, self.other.read(a, b))
        return gated[start - a:start - a + (min(end, self.own.total_samples) - start)]


def open_tracks(session: Session) -> dict[str, object]:
    """Track name -> audio source for transcription (live or afterwards)."""
    raw = {name: TrackAudio(lambda n=name: session.track_files(n)) for name in session.tracks}
    if session.mode != "inperson":
        return raw
    first, second = list(raw)
    return {first: GatedAudio(raw[first], raw[second]), second: GatedAudio(raw[second], raw[first])}
