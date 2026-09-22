from __future__ import annotations


def truncate_text(text: str, limit: int = 30_000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True
