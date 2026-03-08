"""
Token-aware sliding-window text splitter.

Splits a string into overlapping windows measured in tokens.
Uses the HuggingFace tokenizer for the configured dense model when available,
falling back to a fast character-based approximation (÷ 4) otherwise.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Character-to-token ratio used when the real tokenizer cannot be loaded.
_CHARS_PER_TOKEN: float = 4.0


class TokenAwareSplitter:
    """
    Split text into overlapping token-windows.

    Parameters
    ----------
    chunk_size : int
        Target number of tokens per chunk (default 512).
    chunk_overlap : int
        Number of tokens to repeat at the start of the next chunk (default 64).
    model_name : str, optional
        HuggingFace model name whose tokenizer is used for counting.
        When *None* or unavailable, falls back to character estimation.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        model_name: Optional[str] = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._tokenizer = self._load_tokenizer(model_name)

    # ── tokenizer bootstrap ──────────────────────────────────────────────────

    @staticmethod
    def _load_tokenizer(model_name: Optional[str]):
        if not model_name:
            return None
        try:
            from transformers import AutoTokenizer  # type: ignore

            tok = AutoTokenizer.from_pretrained(model_name)
            logger.debug("TokenAwareSplitter: using HF tokenizer for %s", model_name)
            return tok
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TokenAwareSplitter: could not load tokenizer for %s (%s), "
                "falling back to char estimate.",
                model_name,
                exc,
            )
            return None

    # ── public API ───────────────────────────────────────────────────────────

    def count_tokens(self, text: str) -> int:
        """Return the number of tokens in *text*."""
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text, add_special_tokens=False))
        return max(1, int(len(text) / _CHARS_PER_TOKEN))

    def split(self, text: str) -> list[str]:
        """
        Split *text* into window chunks.

        Returns
        -------
        list[str]
            Non-empty chunks; each chunk has at most ``chunk_size`` tokens,
            consecutive chunks share ``chunk_overlap`` tokens of context.
        """
        text = text.strip()
        if not text:
            return []

        # If the whole text fits in one chunk, return as-is.
        if self.count_tokens(text) <= self.chunk_size:
            return [text]

        # Sentence boundaries make for more natural chunk edges.
        sentences = self._split_sentences(text)
        if not sentences:
            return [text]

        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sent_tokens = self.count_tokens(sentence)

            # Single oversized sentence: hard-split by words.
            if sent_tokens > self.chunk_size:
                # Flush current buffer first
                if current:
                    chunks.append(" ".join(current).strip())
                    current, current_tokens = [], 0
                # Hard-split the long sentence
                word_chunks = self._hard_split(sentence)
                chunks.extend(word_chunks[:-1])
                # Carry the last word-chunk into the next sentence
                last = word_chunks[-1]
                current = [last]
                current_tokens = self.count_tokens(last)
                continue

            # Would adding this sentence overflow the window?
            if current_tokens + sent_tokens > self.chunk_size and current:
                chunks.append(" ".join(current).strip())
                # Build overlap from the tail of current buffer
                current, current_tokens = self._build_overlap(current)

            current.append(sentence)
            current_tokens += sent_tokens

        # Flush remainder
        if current:
            chunks.append(" ".join(current).strip())

        return [c for c in chunks if c]

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Naïve sentence splitter on ., !, ? followed by whitespace."""
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def _build_overlap(
        self, sentences: list[str]
    ) -> tuple[list[str], int]:
        """
        Select the trailing sentences from *sentences* that fit within
        ``chunk_overlap`` tokens. Returns (selected_sentences, token_count).
        """
        overlap: list[str] = []
        tokens = 0
        for s in reversed(sentences):
            t = self.count_tokens(s)
            if tokens + t > self.chunk_overlap:
                break
            overlap.insert(0, s)
            tokens += t
        return overlap, tokens

    def _hard_split(self, text: str) -> list[str]:
        """Split oversized text by words when sentence splitting is insufficient."""
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for word in words:
            w_tokens = self.count_tokens(word)
            if current_tokens + w_tokens > self.chunk_size and current:
                chunks.append(" ".join(current))
                # overlap
                overlap, ot = self._build_overlap(current)
                current, current_tokens = overlap, ot
            current.append(word)
            current_tokens += w_tokens

        if current:
            chunks.append(" ".join(current))
        return chunks or [text]
