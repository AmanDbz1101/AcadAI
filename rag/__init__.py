"""Compatibility package exposing `backend.rag` as top-level `rag`.

This keeps legacy imports like `from rag.graph import get_agent` working
when only the project root is on `PYTHONPATH`.
"""

from importlib import import_module
from typing import Any

_backend_rag = import_module("backend.rag")

# Reuse backend.rag package path so `rag.<submodule>` resolves correctly.
__path__ = _backend_rag.__path__

__all__ = getattr(_backend_rag, "__all__", [])


def __getattr__(name: str) -> Any:
    return getattr(_backend_rag, name)
