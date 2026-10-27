"""Find microphones and system-audio (loopback) sources.

`soundcard` covers both platforms:
- Windows: WASAPI; a loopback "microphone" exists for every speaker.
- Linux: PulseAudio/PipeWire; loopback sources are the "Monitor of …" sources.
"""

from __future__ import annotations

from dataclasses import dataclass


def _sc():
    # Imported lazily: on Linux, importing soundcard connects to the audio server.
    import soundcard

    return soundcard


@dataclass
class AudioDevice:
    id: str
    name: str
    is_loopback: bool


def list_inputs() -> list[AudioDevice]:
    sc = _sc()
    return [
        AudioDevice(str(m.id), m.name, bool(m.isloopback))
        for m in sc.all_microphones(include_loopback=True)
    ]


def resolve_mic(device_id: str = ""):
    sc = _sc()
    if device_id:
        try:
            return sc.get_microphone(device_id, include_loopback=False)
        except (IndexError, ValueError):
            pass
    return sc.default_microphone()


def resolve_loopback(device_id: str = ""):
    """System audio. Default: the loopback of the OS default speaker."""
    sc = _sc()
    if device_id:
        try:
            return sc.get_microphone(device_id, include_loopback=True)
        except (IndexError, ValueError):
            pass
    speaker = sc.default_speaker()
    # Matching by name works on both platforms ("X" on Windows, "Monitor of X" on Linux).
    return sc.get_microphone(speaker.name, include_loopback=True)
