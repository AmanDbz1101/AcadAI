"""
Retrieval-specific configuration.
Inherits Qdrant and API settings from the root config.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── resolve root config ────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[4]   # project root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from config import (
        QDRANT_URL,
        QDRANT_API_KEY,
        QDRANT_COLLECTION_NAME,
    )
except ImportError:
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "research_papers")

# ── Model cache (persistent, offline-capable) ───────────────────────────────
MODEL_CACHE_DIR: Path = Path(os.getenv("MODEL_CACHE_DIR", str(_ROOT / "models")))
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Dense embedding ─────────────────────────────────────────────────────────
DENSE_MODEL: str = os.getenv("DENSE_MODEL", "BAAI/bge-small-en-v1.5")
DENSE_VECTOR_SIZE: int = 384          # bge-small-en-v1.5 output dim
DENSE_VECTOR_NAME: str = "dense"      # named vector in Qdrant collection

# ── Sparse embedding ────────────────────────────────────────────────────────
SPARSE_VECTOR_NAME: str = "sparse"    # named sparse vector in Qdrant collection
BM25_ENCODER_DIR: str = os.getenv("BM25_ENCODER_DIR", str(_ROOT / "output"))

# ── Chunking ────────────────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", 512))          # tokens per chunk
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", 64))     # overlap tokens
CHUNK_MIN_CHARS: int = int(os.getenv("CHUNK_MIN_CHARS", 80)) # discard tiny chunks

# ── Retrieval ───────────────────────────────────────────────────────────────
RETRIEVER_TOP_K: int = int(os.getenv("RETRIEVER_TOP_K", 20))  # candidates before rerank
RERANKER_TOP_N: int = int(os.getenv("RERANKER_TOP_N", 5))     # final results after rerank
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "ms-marco-MiniLM-L-12-v2")

# ── Output directory ────────────────────────────────────────────────────────
OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", str(_ROOT / "output")))
