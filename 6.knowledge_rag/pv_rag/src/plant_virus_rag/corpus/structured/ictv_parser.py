"""ICTV Master Species List parser.

Parses the ICTV (International Committee on Taxonomy of Viruses) MSL
spreadsheet/CSV format into PvRecordDTOs.

Expected CSV columns (subset used):
  - Species / Virus Name(s)
  - Virus Abbreviation(s)
  - Genome Composition (ssRNA+, dsDNA, etc.)
  - Host Source (taxonomic classification of host)

The parser is intentionally permissive — skips rows with missing critical
fields rather than failing, so partial datasets still load usefully.
"""

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class PvRecordDTO(BaseModel):
    """Intermediate DTO between parsers and PvStructuredIngestionService."""

    virus_name: str
    virus_abbreviation: str | None = None
    taxonomy: dict | None = None
    host_species: list[str] | None = None
    host_family: str | None = None
    vector: str | None = None
    symptoms: list[str] | None = None
    transmission: str | None = None
    genome_type: str | None = None
    genome_size_kb: float | None = None
    description: str | None = None
    references: list[str] | None = None


class IctvParser:
    """Parses ICTV taxonomy/spreadsheet into PvRecordDTOs.

    Works with both Excel-exported CSV and structured ICTV data dumps.
    Column names are matched case-insensitively.
    """

    def parse(self, file_path: Path) -> Iterator[PvRecordDTO]:
        with open(file_path, encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                dto = self._parse_row(dict(row))
                if dto:
                    yield dto

    def _parse_row(self, row: dict[str, str]) -> PvRecordDTO | None:
        # Normalize keys to lowercase for case-insensitive matching
        norm: dict[str, str] = {k.lower().strip(): v.strip() for k, v in row.items() if v}

        virus_name = self._find(norm, {"species", "virus name(s)", "virus name", "virus_names", "name"})
        if not virus_name:
            return None

        abbreviation = self._find(
            norm, {"virus abbreviation(s)", "virus abbreviation", "abbreviation", "acronym"}
        )
        genome_type = self._find(norm, {"genome composition", "genome", "genome type", "genome_type"})

        host_source = self._find(norm, {"host source", "host_species", "host", "hosts"})
        host_species: list[str] | None = None
        if host_source:
            # ICTV often lists multiple hosts separated by semicolons or commas
            host_species = [h.strip() for h in host_source.replace(";", ",").split(",") if h.strip()]

        order_ = self._find(norm, {"order"})
        family = self._find(norm, {"family"})
        genus = self._find(norm, {"genus"})
        taxonomy: dict | None = None
        if any([order_, family, genus]):
            taxonomy = {}
            if order_:
                taxonomy["order"] = order_
            if family:
                taxonomy["family"] = family
            if genus:
                taxonomy["genus"] = genus

        # Build a textual description from all available fields
        description_parts: list[str] = []
        for k, v in norm.items():
            if k not in {"species", "virus name(s)", "virus name", "name", "virus_names"} and len(v) > 2:
                description_parts.append(f"{k}: {v}")
        description = "\n".join(description_parts) if description_parts else None

        return PvRecordDTO(
            virus_name=virus_name,
            virus_abbreviation=abbreviation,
            taxonomy=taxonomy,
            host_species=host_species,
            genome_type=genome_type,
            description=description,
        )

    @staticmethod
    def _find(norm: dict[str, str], candidates: set[str]) -> str | None:
        for c in candidates:
            if c in norm:
                return norm[c]
        return None
