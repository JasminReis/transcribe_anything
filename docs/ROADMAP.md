# Roadmap

## Phase 0 – Skeleton (now)
- [x] Concept, architecture, project layout
- [x] Device listing, dual-track recording to rotating WAV files
- [x] Transcription after stop (faster-whisper, German default), partial results while running
- [x] Tray icon, recording pill, main window with session library, settings, export TXT/MD/SRT
- [x] Crash recovery (interrupted sessions can be re-transcribed)

## Phase 1 – MVP usable on Windows (target: Ryzen AI 5 330, CPU only)
- [ ] Test capture on the target Windows laptop (Teams, Zoom, headset + speakers)
- [ ] Measure speed of large-v3-turbo / small on that laptop during a running call
- [ ] Transcribe while recording (follow growing files, VAD-based chunks) – needed because the
      laptop has no GPU; worker in a separate process
- [ ] First-run wizard incl. model download progress
- [ ] Search across all transcripts (SQLite FTS5)
- [ ] DOCX export, copy to clipboard
- [ ] Windows build (PyInstaller) + installer + autostart

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
