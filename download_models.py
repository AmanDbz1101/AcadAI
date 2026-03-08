"""
download_models.py — Pre-download and cache all retrieval models locally.

Run once before the first pipeline execution:

    python download_models.py

After this script completes, the pipeline runs fully offline and model loading
is instantaneous (no network calls, no re-downloads after reboot).

Models cached
-------------
- BAAI/bge-small-en-v1.5  → models/sentence_transformers/
- ms-marco-MiniLM-L-12-v2 → models/flashrank/
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
MODEL_CACHE_DIR = ROOT / "models"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = "ms-marco-MiniLM-L-12-v2"


def download_dense_encoder() -> None:
    logger.info("── Dense encoder: %s", DENSE_MODEL)
    t0 = time.time()
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        cache_dir = MODEL_CACHE_DIR / "sentence_transformers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        model = SentenceTransformer(DENSE_MODEL, cache_folder=str(cache_dir))
        dim = model.get_sentence_embedding_dimension()
        elapsed = time.time() - t0
        logger.info("   OK — %d-dim vectors  (%.1fs)  cached at %s", dim, elapsed, cache_dir)
    except Exception as exc:
        logger.error("   FAILED: %s", exc)
        sys.exit(1)


def download_reranker() -> None:
    logger.info("── Reranker: %s", RERANKER_MODEL)
    t0 = time.time()
    try:
        from flashrank import Ranker  # type: ignore

        cache_dir = MODEL_CACHE_DIR / "flashrank"
        cache_dir.mkdir(parents=True, exist_ok=True)
        Ranker(model_name=RERANKER_MODEL, cache_dir=str(cache_dir))
        elapsed = time.time() - t0
        logger.info("   OK — (%.1fs)  cached at %s", elapsed, cache_dir)
    except ImportError:
        logger.error("   FAILED: 'flashrank' not installed — run: pip install flashrank")
        sys.exit(1)
    except Exception as exc:
        logger.error("   FAILED: %s", exc)
        sys.exit(1)


def main() -> None:
    logger.info("Downloading retrieval models → %s", MODEL_CACHE_DIR)
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    download_dense_encoder()
    download_reranker()

    logger.info("All models cached. The pipeline will now load them offline.")


if __name__ == "__main__":
    main()
