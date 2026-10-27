# Distribution – "download, install, use"

Goal: anyone can download one file, double-click it and use Transcribe Anywhere like any other
application. No Python, no git, no command line.

## What the user experiences (Windows)

1. Opens the download page, clicks **TranscribeAnywhere-Setup-1.2.0.exe**.
2. Setup: no admin rights needed (installs per user), Start-menu entry, optional desktop icon,
   optional "start with Windows".
3. First launch: short setup screen → picks the default mic / system audio → downloads the speech
   model (≈1.6 GB, progress bar, one time only).
4. Later: the app says "Version 1.3 available" and links to the new setup file.
5. Uninstall via Windows Settings → Apps; asks whether to keep recordings and transcripts.

Linux: one **AppImage** file (download, make it executable, run).

## How a release is built

```
git tag v1.2.0 && git push --tags
        │
        ▼  GitHub Actions (cloud build machines, no Windows PC needed)
┌───────────────────────────────┐   ┌───────────────────────────────┐
│ windows-latest                │   │ ubuntu-latest                 │
│ pip install .                 │   │ pip install .                 │
│ pyinstaller (packaging/*.spec)│   │ pyinstaller (same spec)       │
│ Inno Setup → Setup.exe        │   │ appimagetool → .AppImage      │
│ sign Setup.exe                │   │                               │
└──────────────┬────────────────┘   └──────────────┬────────────────┘
               └────────────► Release page with both files ◄──────┘
```

The PyInstaller recipe is [packaging/transcribe_anywhere.spec](../packaging/transcribe_anywhere.spec).
It produces one folder with two programs sharing all libraries:

- `Transcribe Anywhere` – the app (no console window)
- `transcribe-anywhere-cli` – command-line tools for testing and support

Build locally: `pip install -e ".[build]"`, then `cd packaging && pyinstaller transcribe_anywhere.spec --noconfirm`.

## Proof of concept (Linux, 2026-10-27)

- Build works; the bundle runs in a clean environment (no venv): device detection, German
  transcription on CPU and app start all OK.
- Size: 540 MB unpacked (speech engine ≈ 145 MB, video/audio decoder ≈ 100 MB, Qt ≈ 120 MB).
  Expected installer size after compression: roughly 150–200 MB, still to measure on Windows.
- NVIDIA libraries are deliberately excluded (would add 1–2 GB; target laptops use the CPU).
- The speech model is not bundled; it is downloaded on first use.

## Decisions needed

| Topic | Options | Recommendation |
|---|---|---|
| Where people download | GitHub Releases (public repo or a separate public "releases" repo) · own website | GitHub Releases: free, versioned, works with the cloud build. A private repo's releases are **not** downloadable by others. |
| Code signing | none · certificate from a certificate authority · Microsoft's cloud signing service | Sign before sharing widely. Unsigned, Windows shows "Windows protected your PC" (users must click *More info → Run anyway*) and antivirus tools are more likely to flag the app. Both paid options need a verified company identity. |
| Bundle the model? | download on first run · "offline" installer with model (~1.8 GB) | Download on first run; offline installer only if needed. |

## Work items (in order)

1. App icon (`.ico` for Windows, `.png` for Linux) and version shown in the app.
2. First-run screen with model download progress (the packaged app has no console).
3. Inno Setup script: per-user install, shortcuts, autostart option, uninstaller.
4. GitHub repository + Actions workflow building Windows and Linux on every version tag.
5. Code signing in the Windows job.
6. Update check (compare own version with the latest release, show a link).
7. "About" dialog with third-party licences (PySide6/Qt is LGPL – fine, because the folder build
   keeps Qt as separate, replaceable libraries; Whisper models and faster-whisper are MIT).
