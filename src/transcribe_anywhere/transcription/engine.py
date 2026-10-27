"""faster-whisper wrapper: model choice, GPU→CPU fallback, German defaults."""

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
    def __init__(self, model: str = "auto", device: str = "auto", language: str = "de", hotwords: str = ""):
        self.model_name = DEFAULT_MODEL if model == "auto" else model
        self.device_pref = device
        self.language = None if language == "auto" else language
        self.hotwords = hotwords.strip() or None
        self.device = ""
        self._model = None

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
