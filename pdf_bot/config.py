"""Configuration loaded from environment variables with sensible defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val  # type: ignore[return-value]


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str = field(default_factory=lambda: _env("BOT_TOKEN", required=True))
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    LOG_FILE: Path = field(default_factory=lambda: Path(_env("LOG_FILE", "bot.log")))

    # Working directory for per-session temp files
    WORK_DIR: Path = field(default_factory=lambda: Path(_env("WORK_DIR", "./sessions")))

    # Hard caps to protect the host
    MAX_IMAGES_PER_PDF: int = field(default_factory=lambda: _env_int("MAX_IMAGES_PER_PDF", 100))
    MAX_FILE_SIZE_MB: int = field(default_factory=lambda: _env_int("MAX_FILE_SIZE_MB", 20))
    # Telegram bots can't download files >20MB via getFile by default; keep aligned
    SESSION_TTL_SECONDS: int = field(default_factory=lambda: _env_int("SESSION_TTL_SECONDS", 3600))

    # Rate limit: minimum seconds between actions per user
    RATE_LIMIT: float = field(default_factory=lambda: float(_env("RATE_LIMIT", "0.5")))

    # OCR
    OCR_LANGUAGES: str = field(default_factory=lambda: _env("OCR_LANGUAGES", "eng"))

    def ensure_dirs(self) -> None:
        self.WORK_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
