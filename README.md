# Transcribe Anywhere

Local meeting transcription for Windows (and Linux): records your microphone **and** the system audio
(Teams, Zoom, Meet, …), transcribes offline with Whisper – German first, English second – and keeps
a searchable library of sessions. Built for long meetings (1–2 h and more).

- Product concept, start and feel: [docs/CONCEPT.md](docs/CONCEPT.md)
- Technical design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Plan: [docs/ROADMAP.md](docs/ROADMAP.md)
- Building a downloadable app: [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)

## Run it (Linux)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"          # add ,cuda for NVIDIA GPU: ".[dev,cuda]"
.venv/bin/transcribe-anywhere                     # tray app + main window
```

## Run it (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"      # add ,cuda if the laptop has an NVIDIA GPU
.venv\Scripts\transcribe-anywhere                 # starts without console window
```

The first transcription downloads the model (`large-v3-turbo`, ≈1.6 GB) into the Hugging Face cache.

## CLI (for testing without UI)

```bash
transcribe-anywhere-cli devices                      # which mic / system audio will be used
transcribe-anywhere-cli record -s 30 -t "Test"       # record 30 s of mic + system audio
transcribe-anywhere-cli transcribe some.wav -d cpu   # transcribe a file, print with timestamps
transcribe-anywhere-cli transcribe-session <folder>  # transcribe a recorded session
```

## Tests

```bash
.venv/bin/pytest
```

## Layout

```
src/transcribe_anywhere/
  __main__.py          entry point (GUI + CLI)
  config.py            settings (JSON in the OS config dir)
  audio/               device lookup, capture threads, rotating WAV writer
  transcription/       faster-whisper engine, session → transcript job
  session/             session folders, transcript JSONL, library/recovery, export
  ui/                  PySide6: tray app, main window, recording pill, settings
  llm/                 optional local AI via Ollama: hardware check, summary, correction
tools/verify_pipeline.py  end-to-end check of silence removal and cutting with a real speech file
tests/                 headless tests of the core
docs/                  concept, architecture, roadmap
```

## First measurements (6.5 min German speech)

| Setup | Time | vs. real time |
|---|---|---|
| RTX 5090, large-v3-turbo float16 | 5 s | ~75× faster |
| CPU only (default 4 threads), large-v3-turbo int8 | 103 s | ~4× faster |
| Simulated laptop (4 cores / 8 threads), large-v3-turbo int8 | 108 s | ~3.6× faster |

Recognition quality on German was very good (punctuation, numbers, technical terms).
The target laptop (Ryzen AI 5 330, no NVIDIA GPU) is expected to manage roughly 1.5–2.5× real time;
details and conclusions in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#target-hardware).
