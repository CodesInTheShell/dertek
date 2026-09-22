from __future__ import annotations

from dertek.exceptions import ProviderNotImplementedError
from dertek.providers.base import LLMProvider
from dertek.providers.openai import OpenAIProvider


def build_provider(name: str) -> LLMProvider:
    normalized = name.strip().lower()
    if normalized == "openai":
        return OpenAIProvider()
    if normalized == "anthropic":
        raise ProviderNotImplementedError(
            "Anthropic Claude support is planned but not implemented in Dertek v0.1."
        )
    if normalized == "gemini":
        raise ProviderNotImplementedError(
            "Google Gemini support is planned but not implemented in Dertek v0.1."
        )
    raise ValueError(f"Unknown provider: {name}")
