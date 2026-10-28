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

    _patch_windows_propvariant()
    return soundcard


def _patch_windows_propvariant() -> None:
    """Fix a heap overflow in soundcard on 64-bit Windows.

    soundcard declares PROPVARIANT as 16 bytes, but it is 24 bytes on x64. Reading a
    device's format (a BLOB property, done for every recording) makes Windows write
    past the allocation, which later crashes the process (0xC0000374 / 0xC0000005).
    Allocate the real size, zero-filled.
    """
    import sys

    if sys.platform != "win32":
        return
    from soundcard import mediafoundation as mf

    if getattr(mf._PropVariant, "_ta_patched", False):
        return

    def __init__(self):
        size = max(24, mf._ffi.sizeof("PROPVARIANT"), mf._ffi.sizeof("BLOB_PROPVARIANT"))
        raw = mf._ole32.CoTaskMemAlloc(size)
        if raw == mf._ffi.NULL:
            raise MemoryError("CoTaskMemAlloc failed")
        mf._ffi.memmove(raw, b"\0" * size, size)
        self.ptr = mf._ffi.cast("PROPVARIANT *", raw)

    def __del__(self):
        mf._ole32.PropVariantClear(self.ptr)
        mf._ole32.CoTaskMemFree(self.ptr)   # the original leaked this block

    mf._PropVariant.__init__ = __init__
    mf._PropVariant.__del__ = __del__
    mf._PropVariant._ta_patched = True


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
