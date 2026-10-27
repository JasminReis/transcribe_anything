"""Meeting summary and transcript correction with a local LLM.

Long meetings do not fit into a small model's context, so both tasks work in parts:
- summary: notes per part ("map"), then one protocol from all notes ("reduce")
- correction: batches of numbered lines; every line keeps its number, timestamp and speaker
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import replace

from transcribe_anywhere.llm.ollama import Ollama
from transcribe_anywhere.session.export import fmt_time
from transcribe_anywhere.session.transcript import Segment

CHARS_PER_TOKEN = 3.0      # German text, conservative
OUTPUT_RESERVE = 2500      # tokens kept free for the answer + instructions

SYSTEM_PROTOCOL = (
    "Du bist ein sorgfältiger Protokollant. Du fasst Besprechungen sachlich und knapp zusammen. "
    "Erfinde nichts. Wenn etwas unklar ist, schreibe das. Antworte in Markdown."
)

PROTOCOL_FORMAT = """Erstelle ein Protokoll mit genau diesen Abschnitten:

## Kurzfassung
3–5 Sätze.

## Themen
Stichpunkte, je Thema ein bis zwei Sätze.

## Entscheidungen
Stichpunkte. „Keine“, wenn es keine gab.

## Aufgaben
Tabelle mit den Spalten Wer | Was | Bis wann. „–“ wenn nicht genannt. „Keine“, wenn es keine gab.

## Offene Fragen
Stichpunkte. „Keine“, wenn es keine gab."""


def transcript_lines(segments: list[Segment]) -> list[str]:
    return [f"[{fmt_time(s.start)}] {s.speaker}: {s.text}" for s in segments]


def split_lines(lines: list[str], max_chars: int) -> list[list[str]]:
    parts, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) > max_chars:
            parts.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append(current)
    return parts


def _language_hint(language: str) -> str:
    return "Antworte auf Englisch." if language == "en" else "Antworte auf Deutsch."


def summarize(
    client: Ollama, model: str, segments: list[Segment], title: str, language: str = "de",
    num_ctx: int = 8192,
    on_token: Callable[[str], None] = lambda t: None,
    on_status: Callable[[str, int, int], None] = lambda text, done, total: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> str:
    budget = int((num_ctx - OUTPUT_RESERVE) * CHARS_PER_TOKEN)
    lines = transcript_lines(segments)
    intro = (f"Hier ist das automatisch erstellte Transkript der Besprechung „{title}“. "
             "Es kann Erkennungsfehler enthalten. „Ich“ ist die Person, die aufgenommen hat; "
             "„Andere“ sind die übrigen Teilnehmenden.")
    parts = split_lines(lines, budget)

    if len(parts) <= 1:
        on_status("Protokoll wird geschrieben", 0, 1)
        prompt = f"{intro}\n\n{PROTOCOL_FORMAT}\n{_language_hint(language)}\n\nTranskript:\n" + "\n".join(lines)
        return client.chat(model, [{"role": "system", "content": SYSTEM_PROTOCOL},
                                   {"role": "user", "content": prompt}],
                           num_ctx, on_token=on_token, should_cancel=should_cancel)

    notes = []
    for i, part in enumerate(parts, 1):
        on_status(f"Teil {i} von {len(parts)} wird gelesen", i - 1, len(parts) + 1)
        prompt = (f"{intro}\n\nDies ist Teil {i} von {len(parts)}. Notiere stichpunktartig: Inhalte, "
                  "Entscheidungen, Aufgaben (mit Person und Termin, falls genannt) und offene Fragen. "
                  "Behalte die Zeitangaben bei. Nur Stichpunkte, keine Einleitung. "
                  f"{_language_hint(language)}\n\nTranskript:\n" + "\n".join(part))
        notes.append(client.chat(model, [{"role": "system", "content": SYSTEM_PROTOCOL},
                                         {"role": "user", "content": prompt}],
                                 num_ctx, should_cancel=should_cancel))

    on_status("Protokoll wird geschrieben", len(parts), len(parts) + 1)
    joined = "\n\n".join(f"### Notizen Teil {i}\n{n}" for i, n in enumerate(notes, 1))
    prompt = (f"Aus der Besprechung „{title}“ liegen Notizen aus {len(parts)} aufeinanderfolgenden Teilen vor. "
              f"Fasse sie zu einem einzigen Protokoll zusammen.\n\n{PROTOCOL_FORMAT}\n"
              f"{_language_hint(language)}\n\n{joined}")
    return client.chat(model, [{"role": "system", "content": SYSTEM_PROTOCOL},
                               {"role": "user", "content": prompt}],
                       num_ctx, on_token=on_token, should_cancel=should_cancel)


SYSTEM_CORRECT = "Du korrigierst automatisch erkannte Sprachtranskripte. Du antwortest nur mit den Zeilen."
_LINE = re.compile(r"^\s*(\d+)\s*\|\s*(.*\S)\s*$")


def correct(
    client: Ollama, model: str, segments: list[Segment], glossary: str = "", num_ctx: int = 8192,
    batch_lines: int = 40,
    on_status: Callable[[str, int, int], None] = lambda text, done, total: None,
    on_batch: Callable[[list[Segment]], None] = lambda segs: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[Segment]:
    result = [replace(s) for s in segments]
    batches = [list(range(i, min(i + batch_lines, len(segments)))) for i in range(0, len(segments), batch_lines)]
    rules = (
        "Korrigiere die folgenden Zeilen eines automatisch erkannten Gesprächs.\n"
        "- Korrigiere nur Hörfehler (falsch erkannte Wörter), Rechtschreibung und Zeichensetzung.\n"
        "- Inhalt, Wortwahl und Umgangssprache NICHT verändern. Nichts kürzen, nichts ergänzen.\n"
        "- Englische Begriffe bleiben englisch.\n"
        "- Format jeder Zeile exakt: Nummer|Text. Gib ALLE Zeilen zurück, auch unveränderte, sonst nichts."
    )
    if glossary.strip():
        rules += f"\n- Richtige Schreibweise von Namen und Fachbegriffen: {glossary.strip()}"
    for b, idx in enumerate(batches):
        on_status(f"Abschnitt {b + 1} von {len(batches)} wird korrigiert", b, len(batches))
        text = "\n".join(f"{i}|{segments[i].text}" for i in idx)
        answer = client.chat(model, [{"role": "system", "content": SYSTEM_CORRECT},
                                     {"role": "user", "content": f"{rules}\n\n{text}"}],
                             num_ctx, temperature=0.0, should_cancel=should_cancel)
        for line in answer.splitlines():
            m = _LINE.match(line)
            if not m:
                continue
            i, new = int(m.group(1)), m.group(2)
            if i in idx and _plausible(segments[i].text, new):
                result[i].text = new
        on_batch(result)
    on_status("Fertig", len(batches), len(batches))
    return result


def _plausible(old: str, new: str) -> bool:
    """Reject answers that rewrite instead of correct (safety net against model creativity)."""
    return difflib.SequenceMatcher(None, old.lower(), new.lower()).ratio() >= 0.6
