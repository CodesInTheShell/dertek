from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]


class ApprovalMode(StrEnum):
    ON_REQUEST = "on-request"
    NEVER = "never"
    AUTO = "auto"


class OpenAIAuthMode(StrEnum):
    API_KEY = "api-key"
    CHATGPT = "chatgpt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DERTEK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: Literal["openai", "anthropic", "gemini"] = "openai"
    openai_auth: OpenAIAuthMode = OpenAIAuthMode.API_KEY
    small_model: str = "gpt-6-luna"
    large_model: str = "gpt-6-sol"
    small_reasoning_effort: ReasoningEffort = "high"
    large_reasoning_effort: ReasoningEffort = "low"
    router_high_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    router_medium_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    max_steps: int = Field(default=12, ge=1, le=100)
    max_jev_calls_per_turn: int = Field(default=4, ge=1, le=20)
    small_model_step_limit: int = Field(default=2, ge=1, le=20)
    jev_verification_enabled: bool = True
    shell_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    approval_mode: ApprovalMode = ApprovalMode.ON_REQUEST

    def workspace(self, value: str | Path | None = None) -> Path:
        return Path(value or Path.cwd()).expanduser().resolve()
