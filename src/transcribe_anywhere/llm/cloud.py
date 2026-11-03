"""Optional cloud AI (Claude or OpenAI): provider choice and API keys.

API keys are kept in the operating system's password store (Windows Credential Manager),
never in settings.json.
"""

from __future__ import annotations

from collections.abc import Callable

PROVIDERS = {"claude": "Claude (Anthropic)", "openai": "OpenAI (ChatGPT)"}
KEY_PAGES = {"claude": "https://console.anthropic.com/settings/keys",
             "openai": "https://platform.openai.com/api-keys"}
_SERVICE = "TranscribeAnywhere"


class CloudError(Exception):
    pass


class Cancelled(Exception):
    pass


def get_key(provider: str) -> str:
    if not provider:
        return ""
    try:
        import keyring

        return keyring.get_password(_SERVICE, provider) or ""
    except Exception:
        return ""


def set_key(provider: str, key: str) -> None:
    import keyring

    key = key.strip()
    if key:
        keyring.set_password(_SERVICE, provider, key)
    else:
        try:
            keyring.delete_password(_SERVICE, provider)
        except Exception:
            pass


def _module(provider: str):
    if provider == "claude":
        from transcribe_anywhere.llm import claude

        return claude
    if provider == "openai":
        from transcribe_anywhere.llm import openai_chat

        return openai_chat
    raise CloudError("Kein Cloud-Anbieter gewählt.")


def default_model(provider: str) -> str:
    return getattr(_module(provider), "DEFAULT_MODEL", "")


def list_models(provider: str, api_key: str) -> list[str]:
    mod = _module(provider)
    try:
        return mod.list_models(api_key)
    except mod.CloudError as e:
        raise CloudError(str(e)) from e


def summarize(provider: str, model: str, prompt: str, transcript: str,
              on_token: Callable[[str], None] = lambda t: None,
              should_cancel: Callable[[], bool] = lambda: False) -> str:
    key = get_key(provider)
    if not key:
        raise CloudError("Kein API-Schlüssel hinterlegt (Einstellungen → KI).")
    mod = _module(provider)
    try:
        return mod.summarize(key, model, prompt, transcript, on_token, should_cancel)
    except mod.Cancelled as e:
        raise Cancelled() from e
    except mod.CloudError as e:
        raise CloudError(str(e)) from e
