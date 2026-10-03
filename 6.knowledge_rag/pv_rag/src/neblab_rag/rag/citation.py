"""Citation parsing and validation.

Extracts [N] markers from generated answers and verifies they reference
chunks that were actually in the prompt. Used by the pipeline (Task 28)
as a soft sanity check — invalid citations don't block the response, but
they're surfaced in the result so the API/UI can flag them.
"""

import re

from pydantic import BaseModel

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def find_citation_numbers(text: str) -> set[int]:
    return {int(m) for m in CITATION_PATTERN.findall(text)}


class CitationValidation(BaseModel):
    is_valid: bool
    referenced_numbers: set[int]
    invalid_numbers: set[int]


def validate_citations(text: str, num_chunks: int) -> CitationValidation:
    referenced = find_citation_numbers(text)
    valid_range = set(range(1, num_chunks + 1))
    invalid = referenced - valid_range
    return CitationValidation(
        is_valid=not invalid,
        referenced_numbers=referenced,
        invalid_numbers=invalid,
    )
