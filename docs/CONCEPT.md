# Transcribe Anywhere – Concept: how the app starts and feels

Name: **Transcribe Anywhere**. The user interface is in German.

## One-sentence pitch

A quiet tray app that records any meeting on your laptop (Teams, Zoom, Meet, phone-over-PC…),
transcribes it **fully offline**, primarily in German and secondarily in English, and hands you a clean,
searchable transcript when the meeting ends — even for sessions of 2+ hours.

## Principles

1. **Invisible until needed.** Lives in the system tray. No window in the way during a meeting.
2. **Never lose a meeting.** Audio goes to disk continuously in small files. A crash, a closed lid or a
   dead battery costs at most a few seconds; the transcript can always be (re)built from disk.
3. **Local only.** No cloud, no account. The network is only used once to download the speech model.
4. **German first.** Default language is German; English and auto-detect are one setting away.
5. **Platform-neutral core.** All logic runs the same on Windows and Linux; only audio capture and
   packaging differ per OS.

## How it starts

| Moment | What the user sees |
|---|---|
| First launch | Main window with a short welcome: pick microphone + "system audio" (auto-filled with defaults), language (Deutsch), model (auto). Model download with progress bar. |
| Normal launch / autostart | Only the tray icon (grey dot). Optional: start with Windows. |
| Second launch while running | Brings the running instance's window to front (single-instance). |

## How a meeting feels

1. **Start**: tray menu → *Aufnahme starten*, the big button in the main window, or (later) a global
   hotkey / an automatic prompt "Teams-Meeting erkannt – aufnehmen?".
2. **Consent reminder** (can be turned off): "Alle Teilnehmenden informiert?" – recording a conversation
   without consent is a criminal offence in Germany (§ 201 StGB), so this belongs in the product.
3. **During the meeting**: a small, draggable, always-on-top **pill** appears:

   ```
   ┌──────────────────────────────────────────────────────┐
   │ ● 00:42:17   Mic ▮▮▮▮▯▯   System ▮▮▯▯▯▯   ⚑   ■     │
   └──────────────────────────────────────────────────────┘
   ```
   - red dot + timer = it is recording
   - two level meters = proof that **both** your voice and the other side are being captured
   - ⚑ = set a marker ("this was important") → shows up in the transcript
   - ■ = stop
   - tray icon turns red
4. **Stop**: pill disappears, tray turns amber ("wird transkribiert"), progress shows in the main window.
   Partial transcript is visible while it is still running.
5. **Done**: notification "Transkript fertig" → click opens the session.

## Main window

```
┌───────────────────────────────────────────────────────────────────────────┐
│ [● Aufnahme starten]  [Meeting-Titel (optional)          ]   ⚙ Einstellungen │
├──────────────────────┬────────────────────────────────────────────────────┤
│ Sitzungen            │ Weekly Sync – 27.10.2026 14:00 · 1:12 h · Fertig    │
│ ───────────────────  │ [Export ▾] [Ordner öffnen] [Neu transkribieren]     │
│ ▸ Weekly Sync        │ ─────────────────────────────────────────────────  │
│   27.10. · 1:12 h ✓  │ 00:00:04  Ich       Guten Morgen zusammen …        │
│ ▸ Kunde X Kickoff    │ 00:00:09  Andere    Hi, können alle mich hören?    │
│   26.10. · 2:03 h ✓  │ 00:14:31  ⚑ Marker                                 │
│ ▸ Interview          │ …                                                  │
│   25.10. · ⚠ unterbr.│                                                    │
└──────────────────────┴────────────────────────────────────────────────────┘
```

- **Left**: session library (newest first) with status: läuft / wartet / wird transkribiert / fertig /
  unterbrochen / Fehler.
- **Right**: transcript with timestamps and speakers, export (TXT, Markdown, SRT; later DOCX), open the
  session folder, re-transcribe (e.g. with a bigger model or another language).
- Closing the window only hides it; the app keeps running in the tray.

## Speakers

- **Phase 1 (free):** mic and system audio are recorded as separate tracks, so we already know
  *"Ich"* (your mic) vs. *"Andere"* (everyone coming through the speakers).
- **Later:** split *"Andere"* into Sprecher 1/2/3 with local speaker diarization, and let the user rename
  speakers.

## Settings (v1)

- Language: Deutsch (default) · Englisch · Automatisch
- Model: Automatisch · large-v3-turbo · large-v3 · medium · small
- Compute: Automatisch (GPU if available) · CPU · GPU
- Microphone, system audio device (defaults follow the OS default devices)
- Storage folder
- Custom vocabulary (names, company and product terms) – improves recognition of jargon
- Consent reminder on/off, start minimized

## Out of scope for v1

Meeting bots, cloud sync, summaries, live captions overlay, mobile. Several are on the roadmap
(see [ROADMAP.md](ROADMAP.md)).
