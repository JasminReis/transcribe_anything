"""Transcript segments and their JSONL storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float      # seconds from session start
    end: float
    text: str
    speaker: str = ""


def write_segments(path: Path, segments: list[Segment]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(asdict(seg), ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_segments(path: Path) -> list[Segment]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [Segment(**json.loads(line)) for line in f if line.strip()]
