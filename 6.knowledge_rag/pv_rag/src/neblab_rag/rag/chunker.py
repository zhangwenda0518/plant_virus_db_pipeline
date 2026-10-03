"""Fixed-size character chunking with overlap.

For Sprint 2 we ship the simplest baseline: split on character count, with
a configurable overlap window so claims spanning a chunk boundary still
have full context in at least one chunk. Char-based (not token-based) on
purpose — works for Chinese and English uniformly without a tokenizer
dependency. Sprint 4 evaluation will tell us whether sentence-aware or
token-based splitting actually moves the quality needle.

Returns ``Chunk`` records with start/end offsets so we can recover the
exact source span (useful for citation cards and overlap math).
"""

from pydantic import BaseModel


class Chunk(BaseModel):
    text: str
    start: int  # inclusive
    end: int  # exclusive


def chunk_text(text: str, *, chunk_size: int = 1500, overlap: int = 300) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size}); "
            "otherwise the window never advances"
        )
    if not text:
        return []

    stride = chunk_size - overlap
    chunks: list[Chunk] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(Chunk(text=text[start:end], start=start, end=end))
        if end >= n:
            break
        start += stride
    return chunks
