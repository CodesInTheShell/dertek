"""UI-neutral application assembly and local persistence for Dertek."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dertek.runtime.storage import (
    AppPaths,
    SessionStore,
    load_settings,
    update_saved_settings,
)

if TYPE_CHECKING:
    from dertek.runtime.factory import DertekRuntime

__all__ = [
    "AppPaths",
    "DertekRuntime",
    "SessionStore",
    "build_runtime",
    "load_settings",
    "update_saved_settings",
]


def __getattr__(name: str) -> Any:
    """Load runtime construction lazily to avoid provider import cycles."""
    if name in {"DertekRuntime", "build_runtime"}:
        from dertek.runtime import factory

        return getattr(factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
