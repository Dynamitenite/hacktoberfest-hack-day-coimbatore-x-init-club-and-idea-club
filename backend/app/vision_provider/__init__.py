"""Server-side vision provider adapter.

``get_provider`` returns the Gemma 4 integration or the deterministic demo
provider. Callers depend only on ``VisionProvider.propose``.
"""

from __future__ import annotations

from ..config import Settings
from .base import ProposeContext, ProviderError, RawProposals, VisionProvider
from .demo import DemoProvider, list_fixtures, match_fixture
from .gemma import GemmaProvider, parse_response
from .normalize import normalize

__all__ = [
    "DemoProvider",
    "GemmaProvider",
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


def get_provider(name: str, settings: Settings) -> VisionProvider:
    if name == "demo":
        return DemoProvider()
    if name == "gemma":
        return GemmaProvider(settings)
    raise ProviderError(f"Unknown provider '{name}'.")
