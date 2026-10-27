"""Entry point.

    transcribe-anywhere              start the tray app
    transcribe-anywhere-cli devices           list microphones and system-audio sources
    transcribe-anywhere-cli record -s 30      record mic + system audio for 30 s (no UI)
    transcribe-anywhere-cli transcribe FILE   transcribe an audio file and print it
    transcribe-anywhere-cli transcribe-session FOLDER
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path


def _cmd_devices(_args) -> int:
    from transcribe_anywhere.audio.devices import list_inputs, resolve_loopback, resolve_mic

    print("Standard-Mikrofon :", resolve_mic().name)
    print("Standard-Systemaudio:", resolve_loopback().name)
    print()
    for d in list_inputs():
        kind = "SYSTEM" if d.is_loopback else "MIC   "
        print(f"  {kind}  {d.name}\n          id={d.id}")
    return 0


def _cmd_record(args) -> int:
    from transcribe_anywhere.audio.capture import SessionRecorder
    from transcribe_anywhere.audio.devices import resolve_loopback, resolve_mic
    from transcribe_anywhere.config import SAMPLE_RATE, SEGMENT_SECONDS, Settings
    from transcribe_anywhere.session.session import Session

    settings = Settings.load()
    storage = Path(args.out) if args.out else settings.storage_path
    session = Session.create(storage, args.title or "", settings.language)
    sources = {"mic": resolve_mic(settings.mic_device), "system": resolve_loopback(settings.loopback_device)}
    rec = SessionRecorder(session.audio_dir, sources, SAMPLE_RATE, SEGMENT_SECONDS)
    print(f"Aufnahme nach {session.folder} – Strg+C zum Beenden")
    rec.start()
    try:
        while args.seconds <= 0 or rec.elapsed < args.seconds:
            lv = rec.levels()
            print(f"\r  {rec.elapsed:6.1f}s  mic={lv.get('mic', 0):.3f}  system={lv.get('system', 0):.3f}  ", end="")
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    session.duration = round(rec.stop(), 1)
    session.status = "recorded"
    session.save()
    print(f"\nFertig: {session.duration}s, Fehler: {rec.errors() or 'keine'}")
    return 0


def _make_transcriber(args):
    from transcribe_anywhere.config import Settings
    from transcribe_anywhere.transcription.engine import Transcriber

    s = Settings.load()
    tr = Transcriber(args.model or s.model, args.device or s.compute_device, args.language or s.language, s.hotwords)
    tr.load(lambda msg: print(msg, file=sys.stderr))
    return tr


def _cmd_transcribe(args) -> int:
    from transcribe_anywhere.session.export import fmt_time

    from transcribe_anywhere.transcription.job import transcribe_chunk
    from transcribe_anywhere.transcription.segmenter import SR, ArrayAudio, detect_speech, plan_chunks

    tr = _make_transcriber(args)
    t0 = time.time()
    audio = ArrayAudio.from_file(Path(args.file))
    if args.no_vad:   # for comparison only: let Whisper see everything, silence included
        segments = tr.transcribe(audio.samples, vad=False)
    else:
        regions = detect_speech(audio)
        speech = sum(e - s for s, e in regions) / SR
        print(f"Sprache: {speech:.0f} s von {audio.total_samples / SR:.0f} s", file=sys.stderr)
        segments = (seg for chunk in plan_chunks(regions) for seg in transcribe_chunk(chunk, audio, tr))
    for seg in segments:
        print(f"[{fmt_time(seg.start)}] {seg.text}", flush=True)
    print(f"({time.time() - t0:.1f}s)", file=sys.stderr)
    return 0


def _cmd_transcribe_session(args) -> int:
    from transcribe_anywhere.session.export import to_txt
    from transcribe_anywhere.session.session import Session
    from transcribe_anywhere.transcription.job import transcribe_session

    session = Session.load(Path(args.folder))
    tr = _make_transcriber(args)
    def show(p):
        print(f"\r  {p.stage:10s} {p.fraction * 100:5.1f} %", end="", file=sys.stderr)

    segments = transcribe_session(session, tr, show)
    print(file=sys.stderr)
    session.status, session.model = "done", f"{tr.model_name} ({tr.device})"
    session.save()
    print(to_txt(session, segments))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="transcribe-anywhere", description="Lokale Meeting-Transkription")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("devices", help="Audiogeräte auflisten")
    rec = sub.add_parser("record", help="Aufnahme ohne Oberfläche")
    rec.add_argument("-s", "--seconds", type=float, default=0, help="Dauer (0 = bis Strg+C)")
    rec.add_argument("-t", "--title", default="")
    rec.add_argument("-o", "--out", default="", help="Speicherort (Standard: Einstellungen)")
    for name, helptext in (("transcribe", "Audiodatei transkribieren"),
                           ("transcribe-session", "Sitzungsordner transkribieren")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("folder" if name == "transcribe-session" else "file")
        p.add_argument("-m", "--model", default="")
        p.add_argument("-l", "--language", default="")
        p.add_argument("-d", "--device", default="")
        if name == "transcribe":
            p.add_argument("--no-vad", action="store_true", help="Stille nicht entfernen (nur zum Vergleich)")
    args = parser.parse_args(argv)

    commands = {"devices": _cmd_devices, "record": _cmd_record,
                "transcribe": _cmd_transcribe, "transcribe-session": _cmd_transcribe_session}
    if args.cmd:
        return commands[args.cmd](args)
    from transcribe_anywhere.ui.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
