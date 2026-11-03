from transcribe_anywhere.llm import tasks
from transcribe_anywhere.llm.hardware import Hardware, advise
from transcribe_anywhere.llm.ollama import find_installed
from transcribe_anywhere.session.transcript import Segment
from transcribe_anywhere.session.export import copy_plain, copy_with_prompt, copy_with_times
from transcribe_anywhere.session.session import Session

SEGS = [Segment(1, 2, "Hallo zusammen.", "Ich"), Segment(3, 4, "Kurze Frage:", "Ich"),
        Segment(5, 6, "Ja, bitte.", "Andere")]


def _session(**kw):
    return Session(folder=None, title="Weekly", started_at="2026-11-03T14:00:00", duration=600, **kw)


def test_copy_formats():
    s = _session()
    assert copy_with_times(s, SEGS).splitlines()[0] == "[14:00:01] Ich: Hallo zusammen."
    assert copy_plain(s, SEGS) == "Ich: Hallo zusammen. Kurze Frage:\n\nAndere: Ja, bitte.\n"
    named = _session(speaker_names={"Andere": "Anna"})
    assert copy_plain(named, SEGS).endswith("Anna: Ja, bitte.\n")


def test_copy_with_prompt_puts_prompt_first():
    text = copy_with_prompt("Fasse zusammen.", _session(), SEGS)
    assert text.startswith("Fasse zusammen.\n\n---\n\nBesprechung: Weekly\nDatum: 03.11.2026 14:00")
    assert "[14:00:05] Andere: Ja, bitte." in text


def test_find_installed_matches_variants():
    installed = ["gemma3:4b-it-q4_K_M", "qwen3.5:9b"]
    assert find_installed("qwen3.5:9b", installed) == "qwen3.5:9b"
    assert find_installed("gemma3:4b", installed) == "gemma3:4b-it-q4_K_M"
    assert find_installed("qwen3.5:27b", installed) is None


def test_advice_for_target_laptop_and_gpu():
    laptop = advise(Hardware("AMD Ryzen AI 5 330", 8, 15.2))
    assert laptop.level == "slow" and not laptop.correction_ok
    assert advise(Hardware("x", 32, 64, "RTX 4070", 12)).correction_ok
    assert advise(Hardware("x", 4, 8)).level == "no"


def test_split_lines_respects_budget():
    parts = tasks.split_lines(["a" * 40] * 10, max_chars=100)
    assert [len(p) for p in parts] == [2, 2, 2, 2, 2]


class FakeClient:
    def __init__(self, answer):
        self.answer = answer

    def chat(self, *args, **kwargs):
        return self.answer


def test_correct_keeps_numbers_and_rejects_rewrites():
    segs = [Segment(0, 1, "Das ist ein Plosis.", "Ich"), Segment(1, 2, "Wir treffen uns morgen.", "Andere"),
            Segment(2, 3, "Unverändert.", "Ich")]
    answer = "0|Das ist ein Plosiv.\n1|Komplett anderer Inhalt ohne Bezug zum Original!\nnoise line"
    out = tasks.correct(FakeClient(answer), "m", segs)
    assert [s.text for s in out] == ["Das ist ein Plosiv.", "Wir treffen uns morgen.", "Unverändert."]
    assert [s.start for s in out] == [0, 1, 2] and segs[0].text == "Das ist ein Plosis."   # original untouched


def test_prompt_default_and_custom():
    from transcribe_anywhere.llm.prompt import DEFAULT_PROMPT, effective_prompt

    assert effective_prompt("") == DEFAULT_PROMPT
    assert effective_prompt("  Nur Aufgaben.  ") == "Nur Aufgaben."


def test_speaker_labels_follow_overlap_and_first_appearance():
    from transcribe_anywhere.transcription.speakers import is_other, label_segments

    segs = [Segment(0, 4, "a", "Andere"), Segment(5, 9, "b", "Andere"), Segment(10, 12, "c", "Andere"),
            Segment(20, 21, "d", "Andere")]
    turns = [(0.0, 4.2, 7), (4.8, 9.5, 3), (9.8, 12.0, 7)]      # diarizer's own speaker ids
    labels = label_segments(segs, turns)
    assert [labels[(s.start, s.end)] for s in segs] == ["Sprecher 1", "Sprecher 2", "Sprecher 1", "Sprecher 1"]
    assert is_other("Andere") and is_other("Sprecher 2") and not is_other("Ich")


def test_cloud_requires_key(monkeypatch):
    import pytest

    from transcribe_anywhere.llm import cloud

    monkeypatch.setattr(cloud, "get_key", lambda provider: "")
    with pytest.raises(cloud.CloudError):
        cloud.summarize("claude", "", "prompt", "transcript")
    assert cloud.default_model("claude") == "claude-opus-5-5"
