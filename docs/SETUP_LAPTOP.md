# Install on the laptop (Windows 11)

About 15 minutes, mostly downloading. Internet is needed once; afterwards everything runs offline.

## 1. Install

1. Copy **`transcribe-anywhere.zip`** to the laptop (USB stick, OneDrive, e-mail …).
2. Right-click the zip → **Alle extrahieren …** → e.g. into `Dokumente\Transcribe Anywhere`.
3. Open that folder and double-click **`install-windows.bat`**.
   - If a blue window says *„Der Computer wurde durch Windows geschützt“*: click
     **Weitere Informationen** → **Trotzdem ausführen**.
   - A window shows the progress. Python and the speech model are downloaded automatically.
     Wait until it says **Fertig!**, then press a key to close it.
4. Start **Transcribe Anywhere** from the desktop icon (also in the Start menu).

## 2. First test (2 minutes)

1. **⚙ Einstellungen**: the defaults are right for this laptop:
   Spracherkennung *Automatisch* (= Parakeet on a laptop without NVIDIA graphics), *Live* ticked,
   Mikrofon and Systemaudio *Systemstandard*.
2. Play any video with speech (e.g. YouTube), then click **● Aufnahme starten** and say a sentence.
3. In the small recording bar (top right) **both meters** (Mic and System) must move, and
   **Live ✓** appears. Text shows up in the main window within a few seconds.
4. Click **■**. The transcript is finished almost immediately → **⧉ Transkript kopieren**.

## 3. Daily use

- The app lives in the taskbar's tray (bottom right, next to the clock). Closing the window
  does not stop it.
- Before a Teams/Zoom meeting: **Aufnahme starten** (optionally enter a title).
  Inform the participants – the app reminds you.
- Use a **headset** if possible. With loudspeakers, the microphone also picks up the other
  participants and their sentences can appear twice.
- After the meeting: copy or export the transcript. **✨ KI-Auswertung** creates a summary if
  [Ollama](https://ollama.com/download) is installed (optional; on this laptop it takes a while,
  the app shows an estimate first).
- Better quality afterwards: **Neu transkribieren ▾ → Mit Whisper** (more accurate, takes
  roughly as long as the meeting itself on this laptop).

## Optional: does live transcription keep up on this laptop?

Drag any audio file with German speech (at least 5 minutes) onto
`tools\windows\check-performance.bat`. It simulates a 10-minute meeting in real time and ends
with **KEEPS UP** or **FALLS BEHIND**. Best run while a Teams/Zoom test call is open.

## Update to a new version

Extract the new zip **over the old folder** (replace files) and run `install-windows.bat`
again. Recordings and settings are kept.

## Where things are stored

| What | Where |
|---|---|
| Recordings, transcripts, summaries | `%LOCALAPPDATA%\TranscribeAnywhere\sessions` (button **Ordner öffnen**) |
| Speech models | `%LOCALAPPDATA%\TranscribeAnywhere\models` |
| Settings | `%LOCALAPPDATA%\TranscribeAnywhere\settings.json` |

**Uninstall:** delete the program folder, the desktop icon and – if the recordings are no
longer needed – `%LOCALAPPDATA%\TranscribeAnywhere`.

## Troubleshooting

| Problem | Solution |
|---|---|
| „System“ meter does not move | Is the meeting sound coming from the default output device? Choose the right *Systemaudio* device in ⚙ Einstellungen. |
| „Mic“ meter does not move | Windows → Einstellungen → Datenschutz → Mikrofon: allow desktop apps. Check the *Mikrofon* setting. |
| Pill shows **Live ⟳ 2:30** (orange) | Live transcription is behind. Nothing is lost – it catches up after the meeting. |
| Installer stops with an error | Run `install-windows.bat` again (it continues where it stopped). Screenshot the error otherwise. |
| Text appears twice | Use a headset (see above). |
