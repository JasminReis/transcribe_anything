"""Meeting summary with OpenAI (official SDK, Responses API, streaming)."""

from __future__ import annotations

import re
from collections.abc import Callable

SYSTEM = ("Du hilfst, Besprechungen zu protokollieren. Halte dich an die Anweisungen des Nutzers "
          "und antworte in Markdown.")
# Chat models only (no embeddings, audio, image, moderation or dated snapshots).
_CHAT = re.compile(r"^(gpt-\d|o\d)")
_SKIP = ("audio", "realtime", "transcribe", "tts", "image", "search", "embedding", "moderation", "codex")


class CloudError(Exception):
    pass


class Cancelled(Exception):
    pass


def _client(api_key: str):
    import openai

    return openai.OpenAI(api_key=api_key, timeout=600.0, max_retries=2)


def list_models(api_key: str) -> list[str]:
    """Chat models this key can use, newest first (also checks that the key works)."""
    import openai

    try:
        models = list(_client(api_key).models.list())
    except openai.AuthenticationError as e:
        raise CloudError("API-Schlüssel ungültig.") from e
    except openai.APIConnectionError as e:
        raise CloudError("Keine Verbindung zu OpenAI. Internet prüfen.") from e
    except openai.APIStatusError as e:
        raise CloudError(f"OpenAI-Fehler {e.status_code}: {e.message}") from e
    chat = [m for m in models if _CHAT.match(m.id) and not any(k in m.id for k in _SKIP)
            and not re.search(r"\d{4}-\d{2}-\d{2}$", m.id)]
    return [m.id for m in sorted(chat, key=lambda m: m.created, reverse=True)]


def summarize(api_key: str, model: str, prompt: str, transcript: str,
              on_token: Callable[[str], None] = lambda t: None,
              should_cancel: Callable[[], bool] = lambda: False) -> str:
    import openai

    if not model:
        models = list_models(api_key)
        if not models:
            raise CloudError("Kein passendes OpenAI-Modell gefunden.")
        model = models[0]
    client = _client(api_key)
    parts: list[str] = []
    try:
        with client.responses.stream(
            model=model,
            instructions=SYSTEM,
            input=f"{prompt}\n\n<transkript>\n{transcript}\n</transkript>",
            max_output_tokens=32000,
        ) as stream:
            for event in stream:
                if should_cancel():
                    raise Cancelled()
                if event.type == "response.output_text.delta":
                    parts.append(event.delta)
                    on_token(event.delta)
            final = stream.get_final_response()
    except openai.AuthenticationError as e:
        raise CloudError("API-Schlüssel ungültig. Bitte in den Einstellungen prüfen.") from e
    except openai.PermissionDeniedError as e:
        raise CloudError("Der API-Schlüssel hat keinen Zugriff auf dieses Modell.") from e
    except openai.NotFoundError as e:
        raise CloudError(f"Modell „{model}“ nicht gefunden. Bitte in den Einstellungen ein anderes wählen.") from e
    except openai.RateLimitError as e:
        raise CloudError("Zu viele Anfragen oder Guthaben aufgebraucht. Bitte später erneut versuchen.") from e
    except openai.APIStatusError as e:
        raise CloudError(f"OpenAI-Fehler {e.status_code}: {e.message}") from e
    except openai.APIConnectionError as e:
        raise CloudError("Keine Verbindung zu OpenAI. Internet prüfen.") from e

    text = "".join(parts) or (final.output_text or "")
    if final.status == "incomplete":
        text += "\n\n*(Antwort wurde abgeschnitten.)*"
    return text
