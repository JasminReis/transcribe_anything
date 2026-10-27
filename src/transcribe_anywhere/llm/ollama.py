"""Minimal Ollama client (standard library only, streaming)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

DEFAULT_URL = "http://localhost:11434"


class OllamaError(Exception):
    pass


class Cancelled(Exception):
    pass


class Ollama:
    def __init__(self, url: str = DEFAULT_URL, extra_options: dict | None = None):
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.extra_options = extra_options or {}   # e.g. {"num_gpu": 0, "num_thread": 4} to force CPU

    def _get(self, path: str, timeout: float = 3):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return json.load(r)

    def _stream(self, path: str, payload: dict, timeout: float = 600):
        req = urllib.request.Request(self.url + path, json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raise OllamaError(_error_text(e)) from e
        except OSError as e:
            raise OllamaError(f"Ollama nicht erreichbar ({self.url}): {e}") from e
        return resp

    def version(self) -> str | None:
        try:
            return self._get("/api/version")["version"]
        except (OSError, ValueError, KeyError):
            return None

    def models(self) -> list[dict]:
        try:
            return [{"name": m["name"], "size_gb": m.get("size", 0) / 1e9}
                    for m in self._get("/api/tags")["models"]]
        except (OSError, ValueError, KeyError):
            return []

    def pull(self, model: str, on_progress: Callable[[float, str], None],
             should_cancel: Callable[[], bool] = lambda: False) -> None:
        with self._stream("/api/pull", {"model": model, "stream": True}, timeout=3600) as resp:
            for line in resp:
                if should_cancel():
                    raise Cancelled()
                msg = json.loads(line)
                if "error" in msg:
                    raise OllamaError(msg["error"])
                total, done = msg.get("total") or 0, msg.get("completed") or 0
                on_progress(done / total if total else -1.0, msg.get("status", ""))

    def chat(self, model: str, messages: list[dict], num_ctx: int = 8192, temperature: float = 0.2,
             on_token: Callable[[str], None] = lambda t: None,
             should_cancel: Callable[[], bool] = lambda: False) -> str:
        options = {"num_ctx": num_ctx, "temperature": temperature, **self.extra_options}
        payload = {"model": model, "messages": messages, "stream": True, "think": False, "options": options}
        try:
            resp = self._stream("/api/chat", payload)
        except OllamaError as e:
            if "think" not in str(e).lower():
                raise
            payload.pop("think")                 # model without a thinking switch
            resp = self._stream("/api/chat", payload)
        parts = []
        with resp:
            for line in resp:
                if should_cancel():
                    raise Cancelled()
                msg = json.loads(line)
                if "error" in msg:
                    raise OllamaError(msg["error"])
                token = msg.get("message", {}).get("content", "")
                if token:
                    parts.append(token)
                    on_token(token)
        return "".join(parts)


def _error_text(e: urllib.error.HTTPError) -> str:
    try:
        return json.loads(e.read()).get("error", str(e))
    except (ValueError, OSError):
        return str(e)


def find_installed(recommended: str, installed: list[str]) -> str | None:
    """Match a recommended tag to what is installed ("gemma3:4b" ↔ "gemma3:4b-it-q4_K_M")."""
    if not recommended:
        return None
    if recommended in installed:
        return recommended
    variants = sorted(n for n in installed if n.startswith(recommended + "-"))
    return variants[0] if variants else None
