"""Turn a recorded session (mic + system tracks) into one merged transcript."""

from __future__ import annotations

from collections.abc import Callable

from transcribe_anywhere.session.session import TRACKS, Session
from transcribe_anywhere.session.transcript import Segment, write_segments
from transcribe_anywhere.transcription.engine import Cancelled, Transcriber


def transcribe_session(
    session: Session,
    transcriber: Transcriber,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[Segment]:
    work = [
        (path, speaker, index * session.segment_seconds)
        for track, speaker in TRACKS.items()
        for index, path in enumerate(session.track_files(track))
    ]
    # Interleave tracks so partial results cover the start of the meeting first.
    work.sort(key=lambda item: item[2])

    segments: list[Segment] = []
    on_progress(0, len(work))
    for done, (path, speaker, offset) in enumerate(work, 1):
        if should_cancel():
            raise Cancelled()
        segments.extend(transcriber.transcribe(path, offset, speaker, should_cancel))
        segments.sort(key=lambda s: s.start)
        write_segments(session.transcript_path, segments)   # partial results visible in the UI
        on_progress(done, len(work))
    return segments
