"""Local Gemma 4 through Ollama (the default provider).

Integration verified against the official docs on 2026-10-08:
  * https://ollama.com/library/gemma4   (tags gemma4:e2b / e4b / 12b / 26b / 31b, all accept image input)
  * https://docs.ollama.com/api/generate (``images`` = base64 list, ``format``, ``stream``, ``keep_alive``)
  * ``GET /api/tags`` lists installed models, ``GET /api/ps`` lists models currently loaded in memory.

One image per analysis, one request, no retries. If Ollama is not running, the
model is not installed, or the call times out, a ``ProviderError`` with setup
instructions is raised. Nothing in this module can fall back to another provider.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

import httpx

from ..config import Settings
from ..schemas import ProviderInfo
from .base import ProposeContext, ProviderError, RawProposals
from .gemma_common import SYSTEM_INSTRUCTION, USER_PROMPT, parse_response

SETUP_STEPS = (
    "Install Ollama from https://ollama.com/download, start it, then run: ollama pull {model}"
)


@dataclass
class OllamaStatus:
    reachable: bool
    model_installed: bool
    model_loaded: bool
    error: Optional[str] = None


def _tagged(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


class OllamaProvider:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport  # tests inject httpx.MockTransport; production uses the real network
        self.info = ProviderInfo(
            name="ollama",
            model=settings.ollama_model,
            runtime=f"Ollama (local, {settings.ollama_host})",
            integration="Ollama /api/generate with one base64 image per request",
            is_demo=False,
        )

    # ------------------------------------------------------------------ helpers

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self.settings.ollama_host, timeout=timeout, transport=self._transport)

    @property
    def setup_hint(self) -> str:
        return SETUP_STEPS.format(model=self.settings.ollama_model)

    def status(self) -> OllamaStatus:
        """Cheap reachability check for /api/health (does not run the model)."""
        want = _tagged(self.settings.ollama_model)
        try:
            with self._client(3.0) as client:
                tags = client.get("/api/tags")
                tags.raise_for_status()
                installed = {_tagged(m.get("name", "")) for m in tags.json().get("models", [])}
                loaded: set[str] = set()
                try:
                    ps = client.get("/api/ps")
                    ps.raise_for_status()
                    loaded = {_tagged(m.get("name", "")) for m in ps.json().get("models", [])}
                except (httpx.HTTPError, ValueError):
                    pass  # /api/ps is informational; installed-ness is what matters
        except (httpx.HTTPError, ValueError) as exc:
            return OllamaStatus(False, False, False, f"Ollama is not reachable at {self.settings.ollama_host} ({type(exc).__name__}).")
        return OllamaStatus(True, want in installed, want in loaded)

    # ------------------------------------------------------------------ inference

    def propose(self, ctx: ProposeContext) -> RawProposals:
        s = self.settings
        payload = {
            "model": s.ollama_model,
            "system": SYSTEM_INSTRUCTION,
            "prompt": USER_PROMPT,
            "images": [base64.b64encode(ctx.annotated_jpeg).decode("ascii")],  # exactly one image
            "stream": False,
            "format": "json",
            "keep_alive": s.ollama_keep_alive,
            "options": {"temperature": 0, "num_ctx": 8192},
        }
        try:
            with self._client(s.gemma_timeout_s) as client:
                response = client.post("/api/generate", json=payload)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Gemma is unavailable: Ollama is not running at {s.ollama_host}. {self.setup_hint}",
                code="unavailable",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Gemma ({s.ollama_model}) did not answer within {s.gemma_timeout_s:g} s. A first request also loads the model, "
                "which can be slow on CPU: try again, or raise GEMMA_TIMEOUT_SECONDS.",
                code="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"The Ollama request failed ({type(exc).__name__}). {self.setup_hint}", code="unavailable") from exc

        if response.status_code == 404:
            raise ProviderError(
                f"Gemma is unavailable: model '{s.ollama_model}' is not installed in Ollama. {self.setup_hint}",
                code="unavailable",
            )
        if response.status_code >= 400:
            detail = _error_detail(response)
            raise ProviderError(
                f"Ollama could not run '{s.ollama_model}' (HTTP {response.status_code}{': ' + detail if detail else ''}). "
                "If the model failed to load, it may not fit in memory: try a smaller tag.",
                code="unavailable",
            )
        try:
            text = str(response.json().get("response", ""))
        except ValueError as exc:
            raise ProviderError("Ollama returned a reply that was not JSON.", code="bad_response") from exc
        if not text.strip():
            raise ProviderError("Gemma returned an empty answer. Try again.", retriable=True, code="bad_response")
        return parse_response(text)


def _error_detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", ""))[:200]
    except ValueError:
        return ""
