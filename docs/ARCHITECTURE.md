# Architecture

## Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best ecosystem for local speech AI; fast to iterate. |
| UI | PySide6 (Qt 6) | Native-looking on Windows and Linux, tray icon, frameless overlay, LGPL. |
| Speech-to-text | faster-whisper (Whisper on CTranslate2) | Runs offline on CPU (int8) and NVIDIA GPU (float16); strong German; built-in Silero VAD. |
| Default model | `large-v3-turbo` | Near large-v3 quality for German at a fraction of the cost. `medium`/`small` for weak laptops. |
| Audio capture | `soundcard` | One API for mic + system audio: WASAPI loopback on Windows, PulseAudio/PipeWire monitor sources on Linux. |
| Paths | `platformdirs` | `%LOCALAPPDATA%\TranscribeAnywhere` on Windows, `~/.local/share/TranscribeAnywhere` on Linux. |
| Packaging | PyInstaller → Inno Setup (Windows), AppImage (Linux) | Later phase. |

## Layers

```
┌──────────────────────────── ui/ (PySide6, only layer that knows Qt) ───────────────────────────┐
│ app.py (tray, single instance)  main_window.py  pill.py  settings_dialog.py  controller.py     │
└───────────────┬────────────────────────────────────────────────────────────────────┬──────────┘
                │ start/stop/marker                                                   │ enqueue
┌───────────────▼──────────────┐   WAV files on disk    ┌─────────────────────────────▼──────────┐
│ audio/                       │ ─────────────────────▶ │ transcription/                          │
│  devices.py  (pick devices)  │  audio/mic_000.wav     │  engine.py  (faster-whisper wrapper,    │
│  capture.py  (1 thread/track)│  audio/system_000.wav  │             GPU→CPU fallback)           │
│  writer.py   (5-min segments)│  …                     │  job.py     (session → transcript)      │
└──────────────────────────────┘                        └─────────────────────────────┬──────────┘
                ┌─────────────────────────────────────────────────────────────────────▼──────────┐
                │ session/  session.py (folder + session.json)  store.py (library, recovery)      │
                │           transcript.py (segments ↔ JSONL)    export.py (TXT/MD/SRT)            │
                └────────────────────────────────────────────────────────────────────────────────┘
```

Everything below `ui/` is plain Python with no Qt dependency, so it can be tested headless and driven
from the CLI (`transcribe-anywhere-cli devices | record | transcribe`).

## Session on disk

```
<storage>/2026-10-27_1400_weekly-sync/
  session.json        id, title, times, status, language, model, markers, segment_seconds
  audio/mic_000.wav   16 kHz mono int16, 5 minutes each (≈ 9.6 MB)
  audio/mic_001.wav
  audio/system_000.wav
  transcript.jsonl    one segment per line: {"start", "end", "speaker", "text"}
```

A 2-hour meeting = 2 tracks × 24 files ≈ 460 MB of WAV. Later: compress finished segments to FLAC/Opus
and offer "delete audio after N days".

## Long sessions (1–2 h and more)

- **Never in RAM**: capture threads write 100 ms blocks straight to the current segment file.
- **Bounded files**: rotating every 5 minutes keeps each file small and limits crash damage.
- **Shared timeline**: each track pads silence when its device delivers nothing (Windows loopback goes
  silent when no sound is playing), so `file_index × 300 s` is always the exact time offset.
- **Recovery**: on startup, sessions still marked `recording`/`transcribing` become `interrupted`; the
  audio is there and can be transcribed with one click.
- **Hallucination guard**: VAD filter on, `condition_on_previous_text=False` (stops Whisper from looping
  on long silences/music).

## Transcription pipeline

v1 (this skeleton): after *Stop*, a background worker transcribes each 5-minute file of both tracks,
merges segments by time, and writes `transcript.jsonl` after every file (partial results are visible).

v2 (planned): transcribe **while recording** – the worker follows the growing files, cuts at VAD
pauses instead of fixed 5-minute borders, and the transcript is ready seconds after the meeting ends.
Run the worker in a separate process so a model crash cannot take down the recorder.

## Platform differences

| | Windows | Linux |
|---|---|---|
| System audio | WASAPI loopback of default speaker | PipeWire/Pulse "Monitor of …" source |
| COM init | needed per capture thread (done in `capture.py`) | – |
| Tray | always available | GNOME needs the AppIndicator extension; app falls back to window |
| GPU | CUDA (NVIDIA) via `pip install .[cuda]`, else CPU int8 | same |
| Packaging | PyInstaller + Inno Setup, autostart via Startup folder | AppImage / .desktop autostart |

## Known risks to verify on Windows early

1. WASAPI loopback + exclusive-mode apps / Bluetooth headsets.
2. CPU speed on the target laptop: `large-v3-turbo` int8 should be faster than real time on a recent
   8-core CPU; otherwise default to `medium` or `small`.
3. Echo when using speakers instead of a headset: the mic track also contains the other side → duplicate
   lines. Mitigation: recommend a headset; later drop mic segments that duplicate system segments.
