"""Server-side vision provider adapter.

``get_provider`` returns exactly the provider the operator configured
(``ollama`` local Gemma 4, ``gemini`` hosted Gemma 4, or the test-only ``demo``).
There is no fallback chain: if the configured provider fails, the caller gets
the error.
"""

from __future__ import annotations

from ..config import Settings
from .base import ProposeContext, ProviderError, RawProposals, VisionProvider
from .demo import DemoProvider, list_fixtures, match_fixture
from .gemini import GeminiProvider
from .gemma_common import parse_response
from .normalize import normalize
from .ollama import OllamaProvider

__all__ = [
    "DemoProvider",
    "GeminiProvider",
    "OllamaProvider",
    "ProposeContext",
    "ProviderError",
    "RawProposals",
    "VisionProvider",
    "get_provider",
    "list_fixtures",
    "match_fixture",
    "normalize",
    "parse_response",
]


def get_provider(settings: Settings) -> VisionProvider:
    name = settings.vision_provider
    if name == "ollama":
        return OllamaProvider(settings)
    if name == "gemini":
        return GeminiProvider(settings)
    if name == "demo":
        return DemoProvider()
    raise ProviderError(f"Unknown provider '{name}'.", code="config")
