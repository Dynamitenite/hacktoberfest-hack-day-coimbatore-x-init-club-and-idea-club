"""Runtime configuration, read once from environment variables.

Secrets (the Gemini API key) are only ever read here, on the server.

There is deliberately no "auto" provider: the provider is exactly the one the
operator configured, and a failure of that provider is reported, never hidden
by switching to another one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# ollama = local Gemma 4 (default), gemini = hosted Gemma 4 via the Gemini API, demo = scripted test fixtures.
PROVIDERS = ("ollama", "gemini", "demo")
DEFAULT_OLLAMA_MODEL = "gemma4:e4b"
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"
ALLOWED_GEMINI_MODELS = {"gemma-4-31b-it", "gemma-4-26b-a4b-it"}


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    for candidate in (BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


_load_dotenv()


class ConfigError(ValueError):
    """The server is configured with a value Wirewise does not support."""


def _provider_from_env() -> str:
    value = os.getenv("VISION_PROVIDER", "ollama").strip().lower() or "ollama"
    if value not in PROVIDERS:
        hint = " The old 'auto' mode was removed because it silently fell back to demo data." if value == "auto" else ""
        raise ConfigError(f"VISION_PROVIDER='{value}' is not supported. Use one of: {', '.join(PROVIDERS)}.{hint}")
    return value


@dataclass(frozen=True)
class Settings:
    vision_provider: str = field(default_factory=_provider_from_env)

    # Local Gemma 4 through Ollama (default provider).
    ollama_host: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip())
    # Seconds a model stays loaded in Ollama after a request (keeps the demo responsive).
    ollama_keep_alive: str = field(default_factory=lambda: os.getenv("OLLAMA_KEEP_ALIVE", "15m").strip())

    # Hosted Gemma 4 through the Gemini API (optional alternative).
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip())
    gemini_image_input: str = field(default_factory=lambda: os.getenv("GEMINI_IMAGE_INPUT", "files").strip().lower())
    gemini_thinking_level: str = field(default_factory=lambda: os.getenv("GEMINI_THINKING_LEVEL", "minimal").strip().lower())

    # One timeout for every model call; no retry loops.
    gemma_timeout_s: float = field(default_factory=lambda: float(os.getenv("GEMMA_TIMEOUT_SECONDS", "60")))

    max_upload_mb: float = field(default_factory=lambda: float(os.getenv("MAX_UPLOAD_MB", "10")))
    session_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_MINUTES", "120")))
    database_path: Path = field(
        default_factory=lambda: Path(os.getenv("WIREWISE_DB_PATH", str(DATA_DIR / "wirewise.db")))
    )
    saved_dir: Path = field(default_factory=lambda: Path(os.getenv("WIREWISE_SAVED_DIR", str(DATA_DIR / "saved"))))
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        ]
    )

    @property
    def is_demo(self) -> bool:
        return self.vision_provider == "demo"


settings = Settings()
