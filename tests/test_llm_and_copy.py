from transcribe_anywhere.llm import tasks
from transcribe_anywhere.llm.hardware import Hardware, advise
from transcribe_anywhere.llm.ollama import find_installed
from transcribe_anywhere.session.transcript import Segment
from transcribe_anywhere.ui.main_window import copy_plain, copy_with_times

SEGS = [Segment(1, 2, "Hallo zusammen.", "Ich"), Segment(3, 4, "Kurze Frage:", "Ich"),
        Segment(5, 6, "Ja, bitte.", "Andere")]


def test_copy_formats():
    assert copy_with_times(SEGS).splitlines()[0] == "[00:00:01] Ich: Hallo zusammen."
    assert copy_plain(SEGS) == "Ich: Hallo zusammen. Kurze Frage:\n\nAndere: Ja, bitte.\n"


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
