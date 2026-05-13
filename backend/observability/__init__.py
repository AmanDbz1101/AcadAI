"""Observability helpers.

Provides a stable `traceable` import for modules that should work
whether or not LangSmith is installed/configured.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


try:  # pragma: no cover - runtime optional dependency
    from langsmith.run_helpers import traceable as _langsmith_traceable

    traceable = _langsmith_traceable
except Exception:  # pragma: no cover - fallback when LangSmith unavailable
    def traceable(*_args: Any, **_kwargs: Any):
        """No-op decorator fallback used when LangSmith is unavailable."""

        def _decorator(fn: F) -> F:
            return fn

        return _decorator


__all__ = ["traceable"]
