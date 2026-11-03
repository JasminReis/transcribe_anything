# Install on the laptop (Windows 11)

About 15 minutes, mostly downloading. Internet is needed once; afterwards everything runs offline
(only the optional Claude/OpenAI summary uses the internet).

## 1. Install

1. Download the program:
   - from GitHub: open the project page, click the green **Code** button → **Download ZIP**, or
   - copy **`transcribe-anywhere.zip`** to the laptop (USB stick, OneDrive, e-mail …).
2. Right-click the zip → **Alle extrahieren …** → e.g. into `Dokumente\Transcribe Anywhere`.
3. Open that folder and double-click **`install-windows.bat`**.
   - If a blue window says *„Der Computer wurde durch Windows geschützt“*: click
     **Weitere Informationen** → **Trotzdem ausführen**.
   - A window shows the progress. Python and the speech model are downloaded automatically.
     Wait until it says **Fertig!**, then press a key to close it.
4. The installer puts **Transcribe Anywhere** (with its violet sound-wave icon) on the desktop and
   in the Start menu.

## 2. Pin it to the taskbar

Windows does not allow programs to pin themselves, so this is one click for you:

- **Start** → type **Transcribe** → right-click **Transcribe Anywhere** → **An Taskleiste anheften**, or
- right-click the desktop icon → **Weitere Optionen anzeigen** → **An Taskleiste anheften**, or
- start the app, right-click its icon in the taskbar → **An Taskleiste anheften**.

Desktop or Start menu icon missing? **⚙ Einstellungen → Allgemein → Verknüpfungen anlegen**
creates both again.

## 3. First test (2 minutes)

1. Next to **● Aufnahme starten**, the mode should be **💻 Online-Meeting**.
2. Play any video with speech (e.g. YouTube), then click **● Aufnahme starten** and say a sentence.
3. In the small recording bar (top right) **both meters** (Mic and System) must move, and
   **Live ✓** appears. Text shows up in the main window within a few seconds, with the time of day.
4. Click **■**. The transcript is finished almost immediately → **⧉ Transkript kopieren**.

The defaults in **⚙ Einstellungen** (or `Strg+,`) are right for this laptop. The settings have
four pages: **Aufnahme** (mode and microphones), **Transkription**, **KI** and **Allgemein**.

## 4. Daily use

### Online meetings (Teams, Zoom, Meet …)

- Mode **💻 Online-Meeting**: records your microphone and the sound of the meeting.
- The app lives in the tray (bottom right, next to the clock). Closing the window does not stop it.
- **Aufnahme starten** (optionally enter a title). Inform the participants – the app reminds you.
- Use a **headset** if possible. With loudspeakers, the microphone also picks up the other
  participants and their sentences can appear twice.
- The microphone button in the recording bar mutes **your** microphone (the meeting keeps
  being recorded). ⚑ sets a marker.

### In-person meetings and interviews (two microphones)

- Mode **🤝 Vor Ort · 2 Mikrofone**: one microphone per person, e.g. you and a client.
  The transcript shows **Ich** and **Gast**.
- The first time, choose **Mikrofon 2 (Gast)** under **⚙ Einstellungen → Aufnahme** (the app
  asks for it). The laptop's built-in microphone plus a USB or headset microphone works.
- **Put each microphone close to its person** (clip-on or small desk microphones are ideal).
  The app keeps each voice only on the microphone where it is loudest, so nothing is written
  twice. Two microphones right next to each other cannot be told apart well.

### After the meeting

- **Who said what:** in online meetings the other participants become **Sprecher 1**,
  **Sprecher 2** … a moment after the transcript is ready (done offline; the first time it
  downloads about 32 MB). **Click a name** (also *Gast* or *Ich*) to enter the real name.
  Not right? **Neu transkribieren ▾ → Nur Sprecher neu erkennen**.
- **Copy:** **⧉ Transkript kopieren ▾** offers *with times*, *plain text*, *Markdown* and
  **✨ Mit KI-Prompt** – prompt plus transcript, ready to paste into ChatGPT, Claude & Co.
  Change the prompt under **Prompt bearbeiten …** (or **Einstellungen → KI**).
- **Delete** a recording you do not need: **🗑 Löschen** (or right-click / `Entf`). It goes to the
  Windows recycle bin.
- **Better quality afterwards:** **Neu transkribieren ▾ → Mit Whisper** (more accurate, takes
  roughly as long as the meeting itself on this laptop).

### AI summary (optional)

The tab **✨ KI-Auswertung** appears once one of these is switched on in **Einstellungen → KI**:

- **Claude or OpenAI:** choose the provider, paste an **API key** and click **Prüfen und Modelle
  laden**. Then **Mit Claude/OpenAI zusammenfassen** writes the summary with your prompt.
  - An API key is **not** included in Claude Pro/Max or ChatGPT Plus. Create one at
    [console.anthropic.com](https://console.anthropic.com/settings/keys) or
    [platform.openai.com](https://platform.openai.com/api-keys); it is billed per use
    (a summary usually costs a few cents).
  - The transcript is sent to the provider – the app asks before the first time.
  - The key is stored in the Windows Credential Manager, not in a file.
  - Without an API key: use **⧉ Transkript kopieren ▾ → ✨ Mit KI-Prompt** and paste into the
    chat you already use.
- **Local AI (Ollama):** runs completely offline, needs [Ollama](https://ollama.com/download)
  and is slow on this laptop (the app shows an estimate first).

## Optional: does live transcription keep up on this laptop?

Drag any audio file with German speech (at least 5 minutes) onto
`tools\windows\check-performance.bat`. It simulates a 10-minute meeting in real time and ends
with **KEEPS UP** or **FALLS BEHIND**. Best run while a Teams/Zoom test call is open.

## Update to a new version

Download the new version (GitHub: **Code → Download ZIP**), extract it **over the old folder**
(replace files) and run `install-windows.bat` again. Recordings, settings and the taskbar pin are
kept.

## Where things are stored

| What | Where |
|---|---|
| Recordings, transcripts, summaries | `%LOCALAPPDATA%\TranscribeAnywhere\sessions` (button **Ordner öffnen**) |
| Speech and speaker models | `%LOCALAPPDATA%\TranscribeAnywhere\models` |
| Settings | `%LOCALAPPDATA%\TranscribeAnywhere\settings.json` |
| Claude/OpenAI API key | Windows Credential Manager (*Anmeldeinformationsverwaltung*), entry `TranscribeAnywhere` |

If Python came from the Microsoft Store, Windows keeps the `TranscribeAnywhere` folder under
`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.11_…\LocalCache\Local\` instead –
**Ordner öffnen** always opens the right one.

**Uninstall:** unpin the icon, delete the program folder and the desktop/Start menu icons
(or run `.venv\Scripts\transcribe-anywhere-cli shortcuts --remove` first) and – if the recordings
are no longer needed – the `TranscribeAnywhere` folder above.

## Troubleshooting

| Problem | Solution |
|---|---|
| „System“ meter does not move | Is the meeting sound coming from the default output device? Choose the right *Systemaudio* device in **Einstellungen → Aufnahme**. |
| „Mic“ meter does not move | Windows → Einstellungen → Datenschutz → Mikrofon: allow desktop apps. Check the *Mikrofon* setting. Is the microphone muted in the recording bar (red, „Stumm“)? |
| „Vor Ort“ does not start | Choose a second, different microphone in **Einstellungen → Aufnahme → Mikrofon 2 (Gast)**. |
| Pill shows **Live ⟳ 2:30** (orange) | Live transcription is behind. Nothing is lost – it catches up after the meeting. |
| Installer stops with an error | Run `install-windows.bat` again (it continues where it stopped). Screenshot the error otherwise. |
| Text appears twice (online) | Use a headset (see above). |
| Text appears twice (Vor Ort) | Move each microphone closer to its person and further from the other one. |
| Wrong names (Sprecher 1/2 mixed up) | Click the name to rename it, or **Neu transkribieren ▾ → Nur Sprecher neu erkennen**. |
| Taskbar shows the Python icon | **Einstellungen → Allgemein → Verknüpfungen anlegen**, unpin the old icon, start the app from the new icon and pin it again. |
| „API-Schlüssel ungültig“ | Copy the key again (it is shown only once when created) and check that billing is set up with the provider. |
