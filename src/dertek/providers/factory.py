from __future__ import annotations

from dertek.config import OpenAIAuthMode
from dertek.exceptions import ProviderNotImplementedError
from dertek.providers.base import LLMProvider
from dertek.providers.openai import OpenAIProvider
from dertek.providers.openai_auth import OpenAIAuthManager, OpenAICredentialStore
from dertek.providers.openai_transport import ChatGPTCodexTransport
from dertek.runtime.storage import AppPaths


def build_provider(
    name: str,
    *,
    openai_auth: OpenAIAuthMode = OpenAIAuthMode.API_KEY,
    paths: AppPaths | None = None,
) -> LLMProvider:
    normalized = name.strip().lower()
    if normalized == "openai":
        if openai_auth == OpenAIAuthMode.CHATGPT:
            auth = OpenAIAuthManager(OpenAICredentialStore(paths))
            return OpenAIProvider(transport=ChatGPTCodexTransport(auth))
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
