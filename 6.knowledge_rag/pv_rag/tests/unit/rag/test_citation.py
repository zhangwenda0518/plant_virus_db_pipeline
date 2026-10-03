"""Tests for citation parsing + validation."""

from neblab_rag.rag.citation import find_citation_numbers, validate_citations


def test_find_citation_numbers_extracts_all_unique() -> None:
    text = "Per [1] and also [2], plus [1] again. [10] is also valid."
    assert find_citation_numbers(text) == {1, 2, 10}


def test_find_citation_numbers_returns_empty_when_no_brackets() -> None:
    assert find_citation_numbers("no citations here") == set()


def test_find_citation_numbers_ignores_non_numeric_brackets() -> None:
    assert find_citation_numbers("see [a] and [foo bar]") == set()


def test_validate_citations_passes_when_all_referenced_exist() -> None:
    result = validate_citations("Per [1] and [2]", num_chunks=3)
    assert result.is_valid is True
    assert result.referenced_numbers == {1, 2}
    assert result.invalid_numbers == set()


def test_validate_citations_fails_when_referencing_nonexistent_chunk() -> None:
    result = validate_citations("Per [5]", num_chunks=3)
    assert result.is_valid is False
    assert 5 in result.invalid_numbers


def test_validate_citations_passes_with_no_citations_when_chunks_empty() -> None:
    result = validate_citations("文献库中暂未找到相关结论。", num_chunks=0)
    assert result.is_valid is True
    assert result.referenced_numbers == set()


def test_validate_citations_fails_when_zero_index_referenced() -> None:
    result = validate_citations("Per [0]", num_chunks=3)
    assert result.is_valid is False
    assert 0 in result.invalid_numbers
