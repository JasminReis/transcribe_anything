import wave

import numpy as np

from transcribe_anywhere.audio.writer import SegmentedWavWriter
from transcribe_anywhere.config import Settings
from transcribe_anywhere.session.export import fmt_time, to_srt, to_txt
from transcribe_anywhere.session.session import Session
from transcribe_anywhere.session.store import list_sessions, recover_interrupted
from transcribe_anywhere.session.transcript import Segment, read_segments, write_segments


def _frames(path):
    with wave.open(str(path)) as w:
        return w.getnframes()


def test_writer_rotates_and_pads(tmp_path):
    w = SegmentedWavWriter(tmp_path, "mic", samplerate=100, segment_seconds=2)  # 200 frames per file
    w.write(np.zeros(150, dtype=np.float32))
    w.write(np.ones(150, dtype=np.float32) * 0.5)
    w.pad_to(450)
    w.close()
    w.write(np.zeros(10, dtype=np.float32))   # ignored after close
    files = sorted(tmp_path.glob("mic_*.wav"))
    assert [_frames(f) for f in files] == [200, 200, 50]
    assert w.total_frames == 450


def test_session_roundtrip_and_recovery(tmp_path):
    s = Session.create(tmp_path, "Kick-off: Kunde Müller")
    assert s.folder.name.endswith("kick-off-kunde-müller")
    s.markers.append(12.5)
    s.save()
    loaded = Session.load(s.folder)
    assert loaded.title == "Kick-off: Kunde Müller" and loaded.markers == [12.5]

    recovered = recover_interrupted(tmp_path)          # status was "recording" -> crash
    assert [r.id for r in recovered] == [s.id]
    assert list_sessions(tmp_path)[0].status == "interrupted"


def test_transcript_and_export(tmp_path):
    s = Session.create(tmp_path, "Test")
    segs = [Segment(3725.5, 3728.0, "Guten Morgen", "Ich"), Segment(1.0, 2.0, "Hallo", "Andere")]
    write_segments(s.transcript_path, segs)
    assert read_segments(s.transcript_path) == segs
    assert fmt_time(3725.5) == "01:02:05"
    assert "[01:02:05] Ich: Guten Morgen" in to_txt(s, segs)
    assert "01:02:05,500 --> 01:02:08,000" in to_srt(s, segs)


def test_settings_ignore_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "en", "obsolete": 1}', "utf-8")
    assert Settings.load(path).language == "en"


def test_muted_track_records_silence_and_keeps_timeline(tmp_path):
    import time

    from transcribe_anywhere.audio.capture import SessionRecorder

    class LoudSource:
        """Fake device that always delivers a loud tone."""

        def recorder(self, samplerate, blocksize):
            src = self

            class Rec:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def record(self, numframes):
                    time.sleep(numframes / samplerate)
                    return np.full((numframes, 2), 0.5, dtype=np.float32)
            return Rec()

    rec = SessionRecorder(tmp_path, {"mic": LoudSource(), "system": LoudSource()}, 1000, 60)
    rec.start()
    time.sleep(0.3)
    rec.set_muted("mic", True)
    assert rec.is_muted("mic") and not rec.is_muted("system")
    time.sleep(0.4)
    assert rec.levels()["mic"] == 0.0 and rec.levels()["system"] > 0.4
    rec.set_muted("mic", False)
    time.sleep(0.3)
    rec.stop()

    def samples(name):
        with wave.open(str(tmp_path / f"{name}_000.wav")) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")

    mic, system = samples("mic"), samples("system")
    assert len(mic) == len(system)                       # muting keeps both tracks in sync
    assert (mic == 0).sum() >= 300                       # ~0.4 s of silence while muted
    assert mic[:200].min() > 0 and mic[-100:].min() > 0  # sound before and after
    assert (system == 0).sum() == 0
