"""Runtime configuration, read once from environment variables.

Secrets (the Gemini API key) are only ever read here, on the server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


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


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    vision_provider: str = field(default_factory=lambda: os.getenv("VISION_PROVIDER", "auto").strip().lower())
    gemma_model: str = field(default_factory=lambda: os.getenv("GEMMA_MODEL", "gemma-4-31b-it").strip())
    gemma_image_input: str = field(default_factory=lambda: os.getenv("GEMMA_IMAGE_INPUT", "files").strip().lower())
    gemma_thinking_level: str = field(default_factory=lambda: os.getenv("GEMMA_THINKING_LEVEL", "minimal").strip().lower())
    gemma_timeout_s: float = field(default_factory=lambda: float(os.getenv("GEMMA_TIMEOUT_SECONDS", "120")))
    max_upload_mb: float = field(default_factory=lambda: float(os.getenv("MAX_UPLOAD_MB", "10")))
    session_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_MINUTES", "120")))
    database_path: Path = field(
        default_factory=lambda: Path(os.getenv("WIREWISE_DB_PATH", str(DATA_DIR / "wirewise.db")))
    )
    saved_dir: Path = field(default_factory=lambda: Path(os.getenv("WIREWISE_SAVED_DIR", str(DATA_DIR / "saved"))))
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if o.strip()
        ]
    )

    @property
    def gemma_available(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def default_provider(self) -> str:
        if self.vision_provider == "demo":
            return "demo"
        if self.vision_provider == "gemma":
            return "gemma"
        return "gemma" if self.gemma_available else "demo"


settings = Settings()

ALLOWED_GEMMA_MODELS = {"gemma-4-31b-it", "gemma-4-26b-a4b-it"}
