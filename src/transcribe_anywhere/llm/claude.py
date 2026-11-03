"""Meeting summary with Claude (Anthropic API, official SDK, streaming)."""

from __future__ import annotations

from collections.abc import Callable

DEFAULT_MODEL = "claude-opus-5-5"
SYSTEM = ("Du hilfst, Besprechungen zu protokollieren. Halte dich an die Anweisungen des Nutzers "
          "und antworte in Markdown.")


class CloudError(Exception):
    pass


class Cancelled(Exception):
    pass


def _client(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=600.0, max_retries=2)


def list_models(api_key: str) -> list[str]:
    """Model ids this key can use, newest first (also checks that the key works)."""
    import anthropic

    try:
        return [m.id for m in _client(api_key).models.list(limit=100)]
    except anthropic.AuthenticationError as e:
        raise CloudError("API-Schlüssel ungültig.") from e
    except anthropic.APIConnectionError as e:
        raise CloudError("Keine Verbindung zu Anthropic. Internet prüfen.") from e
    except anthropic.APIStatusError as e:
        raise CloudError(f"Anthropic-Fehler {e.status_code}: {e.message}") from e


def summarize(api_key: str, model: str, prompt: str, transcript: str,
              on_token: Callable[[str], None] = lambda t: None,
              should_cancel: Callable[[], bool] = lambda: False) -> str:
    import anthropic

    client = _client(api_key)
    parts: list[str] = []
    try:
        # Long transcripts → stream, so the request never hits an HTTP timeout.
        # "fallbacks": if a safety classifier declines, Anthropic retries on its recommended model.
        with client.beta.messages.stream(
            model=model or DEFAULT_MODEL,
            max_tokens=32000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"{prompt}\n\n<transkript>\n{transcript}\n</transkript>"}],
        ) as stream:
            for text in stream.text_stream:
                if should_cancel():
                    raise Cancelled()
                parts.append(text)
                on_token(text)
            final = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise CloudError("API-Schlüssel ungültig. Bitte in den Einstellungen prüfen.") from e
    except anthropic.PermissionDeniedError as e:
        raise CloudError("Der API-Schlüssel hat keinen Zugriff auf dieses Modell.") from e
    except anthropic.NotFoundError as e:
        raise CloudError(f"Modell „{model}“ nicht gefunden. Bitte in den Einstellungen ein anderes wählen.") from e
    except anthropic.RateLimitError as e:
        raise CloudError("Zu viele Anfragen oder Guthaben aufgebraucht. Bitte später erneut versuchen.") from e
    except anthropic.APIStatusError as e:
        raise CloudError(f"Anthropic-Fehler {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise CloudError("Keine Verbindung zu Anthropic. Internet prüfen.") from e

    if final.stop_reason == "refusal":
        raise CloudError("Claude hat die Anfrage abgelehnt.")
    text = "".join(parts)
    if final.stop_reason == "max_tokens":
        text += "\n\n*(Antwort wurde wegen Längenbegrenzung abgeschnitten.)*"
    return text
