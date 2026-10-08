"""Gemma 4 through the hosted Gemini API (optional alternative provider, server side only).

Integration verified against official docs on 2026-10-08:
  * https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api  (models, SDK, image input, thinking)
  * https://ai.google.dev/gemma/docs/capabilities/vision/image (box_2d is [ymin, xmin, ymax, xmax] on a 0-1000 grid)

SDK: ``google-genai`` (``from google import genai``). Models: ``gemma-4-31b-it``
(default) or ``gemma-4-26b-a4b-it``. The documented image path is the Files
API (``client.files.upload``) with the image placed before the text prompt.
Uploaded files are deleted right after the call. The API key is read from the
environment on the server and never reaches the browser.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..config import ALLOWED_GEMINI_MODELS, Settings
from ..schemas import ProviderInfo
from .base import ProposeContext, ProviderError, RawProposals
from .gemma_common import SYSTEM_INSTRUCTION, USER_PROMPT, parse_response


class GeminiProvider:
    def __init__(self, settings: Settings, client=None) -> None:
        if settings.gemini_model not in ALLOWED_GEMINI_MODELS:
            raise ProviderError(
                f"GEMINI_MODEL '{settings.gemini_model}' is not one of the documented Gemma 4 API models: {', '.join(sorted(ALLOWED_GEMINI_MODELS))}.",
                code="config",
            )
        if client is None and not settings.gemini_api_key:
            raise ProviderError(
                "VISION_PROVIDER=gemini but no GEMINI_API_KEY is configured on the server. Add a key to .env, "
                "or switch to the local provider (VISION_PROVIDER=ollama).",
                code="unavailable",
            )
        self.settings = settings
        self._client = client
        self.last_raw_text: str | None = None  # the model's unparsed answer, kept for the proof script
        self.info = ProviderInfo(
            name="gemini",
            model=settings.gemini_model,
            runtime="hosted via Gemini API",
            integration=f"Gemini API via google-genai ({'Files API' if settings.gemini_image_input == 'files' else 'inline bytes'})",
            is_demo=False,
        )

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(self.settings.gemma_timeout_s * 1000)),
            )
        return self._client

    def propose(self, ctx: ProposeContext) -> RawProposals:
        from google.genai import types

        client = self._get_client()
        uploaded = None
        try:
            if self.settings.gemini_image_input == "inline":
                # Not shown in the Gemma docs; offered as an opt-in alternative that keeps the photo off Google's file store.
                image_part = types.Part.from_bytes(data=ctx.annotated_jpeg, mime_type="image/jpeg")
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "breadboard.jpg"
                    path.write_bytes(ctx.annotated_jpeg)
                    uploaded = client.files.upload(file=str(path))
                image_part = uploaded
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_level=self.settings.gemini_thinking_level),
            )
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[image_part, USER_PROMPT],  # image first, as in the docs
                config=config,
            )
            text = response.text or ""
        except ProviderError:
            raise
        except Exception as exc:  # network, quota, auth ... never echo the key or raw payloads
            message, code = _safe_error(exc, self.settings.gemini_api_key)
            raise ProviderError(message, retriable=True, code=code) from exc
        finally:
            if uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass
        self.last_raw_text = text
        if not text.strip():
            raise ProviderError("Gemma returned an empty answer. Try again.", retriable=True, code="bad_response")
        return parse_response(text)


def _safe_error(exc: Exception, key: str) -> tuple[str, str]:
    """(message, code). The message never contains the API key or a raw payload."""
    name = type(exc).__name__
    msg = str(exc)
    if key:
        msg = msg.replace(key, "***")
    lowered = msg.lower()
    if "api key" in lowered or "permission" in lowered or "401" in lowered or "403" in lowered:
        return "The Gemini API rejected the request (check GEMINI_API_KEY and that Gemma 4 is enabled for your project).", "unavailable"
    status = getattr(exc, "code", None)
    if status in (500, 502, 503, 504) or any(t in lowered for t in ("unavailable", "deadline", "overloaded", "high demand", "internal")):
        return (
            f"The Gemini API is temporarily overloaded or failed on its side (HTTP {status or '5xx'}). "
            "Nothing was analyzed and Wirewise does not retry or fall back. Wait a moment and press the button again.",
            "unavailable",
        )
    if "429" in lowered or "quota" in lowered or "rate" in lowered:
        return "The Gemini API rate limit or quota was reached. Wait a moment and try again.", "unavailable"
    if "timeout" in lowered or "timed out" in lowered or "connect" in lowered:
        return "Could not reach the Gemini API in time. Check the network and try again.", "timeout"
    return f"The Gemma request failed ({name}). Try again.", "failed"
