"""The editable meeting prompt: used for "copy with prompt" and for Claude/OpenAI summaries."""

from __future__ import annotations

DEFAULT_PROMPT = """Du bekommst unten das automatisch erstellte Transkript einer Besprechung. Es kann Erkennungsfehler enthalten.
„Ich“ ist die Person, die aufgenommen hat. „Gast“, „Sprecher 1“, „Sprecher 2“ usw. (oder „Andere“) sind die übrigen Teilnehmenden, sofern sie nicht mit Namen eingetragen sind. Die Zeitangaben sind Uhrzeiten.

Erstelle ein sachliches Protokoll auf Deutsch mit genau diesen Abschnitten:

## Kurzfassung
3–5 Sätze.

## Themen
Stichpunkte, je Thema ein bis zwei Sätze.

## Entscheidungen
Stichpunkte. „Keine“, wenn es keine gab.

## Aufgaben
Tabelle mit den Spalten Wer | Was | Bis wann. „–“, wenn nicht genannt. „Keine“, wenn es keine gab.

## Offene Fragen
Stichpunkte. „Keine“, wenn es keine gab.

Erfinde nichts. Wenn etwas unklar ist, schreibe das."""


def effective_prompt(custom: str) -> str:
    return custom.strip() or DEFAULT_PROMPT
