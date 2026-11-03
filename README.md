# Transcribe Anywhere

Local meeting transcription for Windows (and Linux): records your microphone **and** the system audio
(Teams, Zoom, Meet, …), transcribes offline with Whisper – German first, English second – and keeps
a searchable library of sessions. Built for long meetings (1–2 h and more).

- **Online meetings** (mic + system audio) or **in-person meetings** with two microphones
  (e.g. an interview with a client) – each microphone keeps only its own person's voice.
- Transcript with **time of day** and **who said what**: other participants are told apart offline
  (*Sprecher 1*, *Sprecher 2* …) and can be renamed with a click.
- Copy the transcript **with an editable AI prompt** for ChatGPT/Claude, or let **Claude or OpenAI**
  (own API key, optional) or a **local Ollama model** (optional) write the summary.
- Windows app icon and shortcuts – pin it to the taskbar like any other program.

**Install on a Windows laptop: [docs/SETUP_LAPTOP.md](docs/SETUP_LAPTOP.md)** – download the ZIP
(green **Code** button → **Download ZIP**), extract it, double-click `install-windows.bat`, then pin
**Transcribe Anywhere** to the taskbar (right-click → *An Taskleiste anheften*).

More:
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
.venv\Scripts\transcribe-anywhere-cli shortcuts   # desktop + Start menu icon (then pin to taskbar)
```

The first transcription downloads the model (`large-v3-turbo`, ≈1.6 GB) into the Hugging Face cache.

## CLI (for testing without UI)

```bash
transcribe-anywhere-cli devices                      # which mic / system audio will be used
transcribe-anywhere-cli shortcuts                    # Windows: desktop/Start menu icons (--remove)
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
  transcription/       engines (Whisper, Parakeet), silence removal/cutting, live + full jobs,
                       speakers.py (offline speaker detection), crosstalk.py (two-microphone mode)
  session/             session folders, transcript JSONL, library/recovery, export (time of day)
  ui/                  PySide6: tray app, main window, recording pill, settings (sidebar pages)
  llm/                 AI summaries: prompt.py (editable prompt), cloud.py + claude.py + openai_chat.py
                       (optional, API key in the OS keyring), Ollama (optional local AI)
  winshortcut.py       Windows app ID, icon and shortcuts (taskbar pinning)
  assets/app.ico       application icon
tools/verify_pipeline.py  end-to-end check of silence removal and cutting with a real speech file
tools/simulate_live.py    plays a fake meeting through the recorder to test live transcription
tools/windows/            installer script and performance check for Windows
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
