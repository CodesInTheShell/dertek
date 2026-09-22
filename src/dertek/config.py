from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DERTEK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: Literal["openai", "anthropic", "gemini"] = "openai"
    model: str = "gpt-5.5"
    router_high_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    router_medium_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    max_steps: int = Field(default=12, ge=1, le=100)
    shell_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    approval_mode: Literal["on-request", "never"] = "on-request"

    def workspace(self, value: str | Path | None = None) -> Path:
        return Path(value or Path.cwd()).expanduser().resolve()
