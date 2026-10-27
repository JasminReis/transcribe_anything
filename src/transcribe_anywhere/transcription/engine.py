"""Speech-to-text engines.

- Whisper (faster-whisper): most accurate, language can be fixed to German, slow on CPU.
- Parakeet TDT 0.6B v3 (NVIDIA, via onnx-asr): ~8× faster on CPU, never invents text on silence,
  detects German/English itself. Default on computers without an NVIDIA GPU.

Both take speech-only chunks (see segmenter.py) and yield Segments.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

from transcribe_anywhere.session.transcript import Segment
from transcribe_anywhere.transcription.filters import is_hallucination

log = logging.getLogger(__name__)

# On CPU, "medium" was no faster than large-v3-turbo and less accurate, so it is not offered.
MODELS = ["large-v3-turbo", "large-v3", "small"]
DEFAULT_MODEL = "large-v3-turbo"


class Cancelled(Exception):
    pass


def _preload_pip_cuda_libs() -> None:
    """Make pip-installed NVIDIA libs (extra `cuda`) findable for CTranslate2."""
    import ctypes
    import importlib.util

    for pkg, names in (
        ("nvidia.cublas", ["libcublasLt.so.12", "libcublas.so.12"]),
        ("nvidia.cudnn", ["libcudnn.so.9"]),
    ):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        if not spec or not spec.submodule_search_locations:
            continue
        libdir = Path(list(spec.submodule_search_locations)[0]) / ("bin" if sys.platform == "win32" else "lib")
        if sys.platform == "win32":
            import os

            if libdir.exists():
                os.add_dll_directory(str(libdir))
            continue
        for name in names:
            try:
                ctypes.CDLL(str(libdir / name), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
        if pkg == "nvidia.cudnn":  # cuDNN 9 loads its sub-libraries on demand
            for sub in sorted(libdir.glob("libcudnn_*.so.9")):
                try:
                    ctypes.CDLL(str(sub), mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    """Whisper engine (faster-whisper)."""

    engine = "whisper"

    def __init__(self, model: str = "auto", device: str = "auto", language: str = "de", hotwords: str = ""):
        self.model_name = DEFAULT_MODEL if model == "auto" else model
        self.device_pref = device
        self.language = None if language == "auto" else language
        self.hotwords = hotwords.strip() or None
        self.device = ""
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def label(self) -> str:
        return f"Whisper {self.model_name} ({self.device or '?'})"

    def load(self, status: Callable[[str], None] = lambda _msg: None) -> None:
        from faster_whisper import WhisperModel

        candidates = []
        if self.device_pref in ("auto", "cuda") and cuda_available():
            _preload_pip_cuda_libs()
            candidates.append(("cuda", "float16"))
        if self.device_pref in ("auto", "cpu") or not candidates:
            candidates.append(("cpu", "int8"))

        last_error: Exception | None = None
        for device, compute_type in candidates:
            status(f"Lade Modell {self.model_name} ({device.upper()}) …")
            try:
                model = WhisperModel(self.model_name, device=device, compute_type=compute_type)
                # Warm-up: CUDA problems (missing cuDNN, unsupported GPU) only show on first use.
                list(model.transcribe(np.zeros(16_000, dtype=np.float32), language="de", vad_filter=False)[0])
            except Exception as exc:
                log.warning("Model on %s failed: %s", device, exc)
                last_error = exc
                continue
            self._model, self.device = model, device
            status(f"Modell {self.model_name} bereit ({device.upper()})")
            return
        raise RuntimeError(f"Modell konnte nicht geladen werden: {last_error}")

    def transcribe(
        self,
        audio: str | Path | np.ndarray,
        offset: float = 0.0,
        speaker: str = "",
        should_cancel: Callable[[], bool] = lambda: False,
        vad: bool = True,
    ) -> Iterator[Segment]:
        """Yield segments. Pass vad=False for audio that already contains only speech."""
        if self._model is None:
            self.load()
        segments, _info = self._model.transcribe(
            str(audio) if isinstance(audio, Path) else audio,
            language=self.language,
            beam_size=5,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 1000, "speech_pad_ms": 400} if vad else None,
            condition_on_previous_text=False,   # avoids repetition loops in long audio
            hotwords=self.hotwords,
        )
        for seg in segments:
            if should_cancel():
                raise Cancelled()
            if is_hallucination(seg.text, seg.no_speech_prob, seg.avg_logprob):
                continue
            yield Segment(round(offset + seg.start, 2), round(offset + seg.end, 2), seg.text.strip(), speaker)


# --------------------------------------------------------------------------- Parakeet
PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"
PARAKEET_FILES = ["config.json", "vocab.txt", "nemo128.onnx",
                  "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx"]   # ≈ 670 MB


def parakeet_dir() -> Path:
    from transcribe_anywhere.config import models_dir

    return models_dir() / "parakeet-tdt-0.6b-v3-int8"


def ensure_parakeet(status: Callable[[str], None] = lambda _m: None) -> Path:
    """Download the int8 model into a plain folder once.

    A plain folder (not the Hugging Face cache with its links) is needed: onnxruntime refuses
    model data that lives behind links outside the model folder.
    """
    target = parakeet_dir()
    if all((target / f).exists() for f in PARAKEET_FILES):
        return target
    status("Parakeet-Modell wird heruntergeladen (≈ 670 MB, nur beim ersten Mal) …")
    from huggingface_hub import snapshot_download

    snapshot_download(PARAKEET_REPO, local_dir=target, allow_patterns=PARAKEET_FILES)
    return target


def tokens_to_segments(tokens: list[str], times: list[float], max_gap: float = 1.0,
                       max_words: int = 40) -> list[tuple[float, float, str]]:
    """Group Parakeet tokens (" Der", "Ar", "ti", "kel", ".") into sentence-like segments."""
    out: list[tuple[float, float, str]] = []
    cur: list[str] = []
    start = last = 0.0

    def flush(end: float) -> None:
        text = "".join(cur).strip()
        if text:
            out.append((start, max(end, start + 0.2), text))
        cur.clear()

    for i, (tok, t) in enumerate(zip(tokens, times)):
        new_word = tok.startswith(" ")
        if cur and new_word and (t - last > max_gap or len("".join(cur).split()) >= max_words):
            flush(last + 0.3)
        if not cur:
            start = t
        cur.append(tok)
        last = t
        text = "".join(cur).rstrip()
        nxt = tokens[i + 1] if i + 1 < len(tokens) else " "
        # sentence end – but not "16. Februar" (digit before the dot)
        if text.endswith((".", "?", "!")) and nxt.startswith(" ") and not (
                text.endswith(".") and len(text) > 1 and text[-2].isdigit()):
            flush(t + 0.3)
    if cur:
        flush(last + 0.4)
    return out


class ParakeetTranscriber:
    """NVIDIA Parakeet TDT 0.6B v3 (int8, CPU) via onnx-asr."""

    engine = "parakeet"
    model_name = "parakeet-tdt-0.6b-v3"

    def __init__(self, threads: int = 0):
        import os

        self.threads = threads or max(1, min(4, (os.cpu_count() or 2) // 2))  # leave room for Teams/Zoom
        self.device = "cpu"
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def label(self) -> str:
        return "Parakeet v3 (CPU)"

    def load(self, status: Callable[[str], None] = lambda _msg: None) -> None:
        import onnx_asr
        import onnxruntime as ort

        path = ensure_parakeet(status)
        status("Lade Parakeet v3 …")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.threads
        opts.inter_op_num_threads = 1
        self._model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", path, quantization="int8",
                                          sess_options=opts).with_timestamps()
        status("Parakeet v3 bereit (CPU)")

    def transcribe(self, audio, offset: float = 0.0, speaker: str = "",
                   should_cancel: Callable[[], bool] = lambda: False, vad: bool = True) -> Iterator[Segment]:
        """`vad` is ignored: Parakeet does not invent text on silence; chunks come pre-cut."""
        if self._model is None:
            self.load()
        if should_cancel():
            raise Cancelled()
        if isinstance(audio, (str, Path)):
            from transcribe_anywhere.transcription.segmenter import ArrayAudio

            audio = ArrayAudio.from_file(Path(audio)).samples
        if len(audio) < 1600:           # < 0.1 s
            return
        result = self._model.recognize(np.asarray(audio, dtype=np.float32))
        for start, end, text in tokens_to_segments(result.tokens or [], result.timestamps or []):
            if not is_hallucination(text):
                yield Segment(round(offset + start, 2), round(offset + end, 2), text, speaker)


# --------------------------------------------------------------------------- factory
ENGINES = {"auto": "Automatisch", "whisper": "Whisper", "parakeet": "Parakeet"}


def resolve_engine(engine: str, device: str = "auto") -> str:
    """auto → Whisper on an NVIDIA GPU, Parakeet otherwise (laptops)."""
    if engine in ("whisper", "parakeet"):
        return engine
    if device == "cpu":
        return "parakeet"
    return "whisper" if cuda_available() else "parakeet"


def create_transcriber(engine: str = "auto", model: str = "auto", device: str = "auto",
                       language: str = "de", hotwords: str = ""):
    if resolve_engine(engine, device) == "parakeet":
        return ParakeetTranscriber()
    return Transcriber(model, device, language, hotwords)
