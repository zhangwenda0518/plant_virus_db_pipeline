"""Tests for the Chunker — fixed-size character chunking with overlap.

Char-based (not token-based) on purpose: works for both Chinese and
English without a tokenizer dependency, and the size→token ratio is
stable enough for v1. Sprint 4 evaluation will tell us whether to
upgrade to sentence-aware or token-aware splitting.
"""

import pytest

from neblab_rag.rag.chunker import Chunk, chunk_text


def test_short_text_returns_single_chunk() -> None:
    chunks = chunk_text("hello world", chunk_size=500, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].start == 0
    assert chunks[0].end == 11


def test_empty_text_returns_empty_list() -> None:
    assert chunk_text("", chunk_size=500, overlap=100) == []


def test_long_text_splits_with_overlap() -> None:
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=400, overlap=100)
    # stride = 400 - 100 = 300; chunks at [0:400], [300:700], [600:1000]
    assert len(chunks) == 3
    assert chunks[0].start == 0 and chunks[0].end == 400
    assert chunks[1].start == 300 and chunks[1].end == 700
    assert chunks[2].start == 600 and chunks[2].end == 1000
    # Overlap region must match between consecutive chunks
    assert text[300:400] == chunks[0].text[-100:] == chunks[1].text[:100]


def test_text_exactly_chunk_size_returns_single_chunk() -> None:
    text = "x" * 500
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_last_chunk_may_be_smaller_than_chunk_size() -> None:
    # 500 + (overlap=100, stride=400) → next chunk starts at 400, ends at 750
    text = "y" * 750
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) == 2
    assert chunks[0].end == 500
    assert chunks[1].start == 400 and chunks[1].end == 750
    assert len(chunks[1].text) == 350  # smaller than chunk_size, OK


def test_chunks_cover_entire_text() -> None:
    """Every character of the input must appear in at least one chunk."""
    text = "the quick brown fox jumps over the lazy dog " * 20  # 880 chars
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    reconstructed = ""
    cursor = 0
    for c in chunks:
        # Skip overlap region — append only the new chars beyond cursor
        new_part = c.text[max(0, cursor - c.start) :]
        reconstructed += new_part
        cursor = c.end
    assert reconstructed == text


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("abc", chunk_size=10, overlap=10)


def test_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("abc", chunk_size=0, overlap=0)


def test_chunks_handle_chinese_text() -> None:
    text = "北方生态屏障数字实验室是中国国家级生态项目" * 30  # 600 chars (CN)
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) >= 3
    assert all(isinstance(c, Chunk) for c in chunks)
    # No char loss
    assert chunks[0].text[0] == text[0]
    assert chunks[-1].text[-1] == text[-1]
