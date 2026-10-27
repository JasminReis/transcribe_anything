# Roadmap

## Phase 0 – Skeleton and core quality (done)
- [x] Concept, architecture, project layout
- [x] Device listing, dual-track recording to rotating WAV files
- [x] Transcription after stop (faster-whisper, German default), partial results while running
- [x] Tray icon, recording pill, main window with session library, settings, export TXT/MD/SRT
- [x] Crash recovery (interrupted sessions can be re-transcribed)
- [x] Silence/noise removal before Whisper, cutting only at pauses, exact meeting timestamps
- [x] Phantom-phrase filter; verification tool with real speech (`tools/verify_pipeline.py`)
- [x] Animated progress card (stages, speed, remaining time, live sentence)
- [x] Copy transcript (with times / plain text / Markdown), Original ↔ KI-korrigiert view
- [x] Local AI via Ollama: hardware check, model recommendation + download, summary, correction

## Phase 1 – MVP usable on Windows (target: Ryzen AI 5 330, CPU only)
- [ ] Test capture on the target Windows laptop (Teams, Zoom, headset + speakers)
- [ ] Measure speed of large-v3-turbo / small on that laptop during a running call
- [x] Transcribe while recording (follows the growing files, same cutting as offline)
- [x] Parakeet v3 engine (8× faster than Whisper on CPU) – default without NVIDIA GPU
- [x] Windows installer (`install-windows.bat`) + laptop guide + performance check
- [ ] Run the installer and a real Teams/Zoom call on the laptop (installer untested on Windows!)
- [ ] Worker in a separate process (a crash in the recogniser cannot stop the recording)
- [ ] First-run wizard incl. model download progress
- [ ] Search across all transcripts (SQLite FTS5)
- [ ] DOCX export, copy to clipboard
- [x] PyInstaller recipe, standalone bundle tested on Linux
- [ ] Downloadable app: Setup.exe + AppImage built in the cloud, signed, update check
      (details: [DISTRIBUTION.md](DISTRIBUTION.md))

## Phase 2 – Comfort
- [ ] Global hotkey start/stop, pause
- [ ] Echo de-duplication between mic and system track
- [ ] Compress finished audio (FLAC/Opus), retention setting

## Phase 3 – Smart
- [ ] Meeting detection (Teams/Zoom process uses the mic → "Aufnehmen?")
- [ ] Speaker diarization for the "Andere" track, renameable speakers
- [ ] Optional local summary / action items via a local LLM
- [ ] Evaluate German fine-tuned Whisper variants against large-v3-turbo
- [ ] Evaluate the Ryzen AI NPU (AMD Ryzen AI software / ONNX Whisper) to offload the CPU
