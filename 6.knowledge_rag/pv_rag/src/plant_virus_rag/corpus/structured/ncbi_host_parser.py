"""NCBI host-virus association parser.

NCBI hosts database provides virus-host interactions with taxonomic
identifiers. This parser handles tabular exports mapping virus species
to their known host species (plants).

Expected columns (subset used):
  - Virus taxid / Virus name
  - Host taxid / Host name / Host family
  - Evidence (publication/source)
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO


class NcbiHostParser:
    """Parses NCBI host-pathogen interaction data into PvRecordDTOs."""

    def parse(self, file_path: Path) -> Iterator[PvRecordDTO]:
        with open(file_path, encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                dto = self._parse_row(dict(row))
                if dto:
                    yield dto

    def _parse_row(self, row: dict[str, str]) -> PvRecordDTO | None:
        norm: dict[str, str] = {k.lower().strip(): v.strip() for k, v in row.items() if v}

        virus_name = self._find(
            norm,
            {
                "virus name", "virus_name", "virus", "scientific name",
                "species", "virus species", "virus_species",
            },
        )
        if not virus_name:
            return None

        host_name = self._find(
            norm,
            {"host name", "host_name", "host", "host scientific name", "host species", "host_species"},
        )
        host_species: list[str] | None = None
        if host_name:
            host_species = [host_name]

        host_family = self._find(norm, {"host family", "host_family", "family"})

        host_taxid = self._find(norm, {"host taxid", "host_taxid", "host taxonomy id"})
        virus_taxid = self._find(norm, {"virus taxid", "virus_taxid", "taxid"})

        reference = self._find(norm, {"evidence", "reference", "pubmed id", "pmid", "source"})
        references: list[str] | None = None
        if reference:
            references = [reference]

        # Build description
        desc_parts = []
        if host_name:
            desc_parts.append(f"Host: {host_name}")
        if host_family:
            desc_parts.append(f"Host family: {host_family}")
        if host_taxid:
            desc_parts.append(f"Host taxid: {host_taxid}")
        if virus_taxid:
            desc_parts.append(f"Virus taxid: {virus_taxid}")

        for k, v in norm.items():
            if len(v) > 3 and k not in {
                "virus name", "virus_name", "virus", "scientific name",
                "species", "virus species", "virus_species",
                "host name", "host_name", "host", "host scientific name",
                "host species", "host_species",
                "host family", "host_family", "family",
                "host taxid", "host_taxid", "host taxonomy id",
                "virus taxid", "virus_taxid", "taxid",
                "evidence", "reference", "pubmed id", "pmid", "source",
            }:
                desc_parts.append(f"{k}: {v}")

        description = "\n".join(desc_parts) if desc_parts else None

        return PvRecordDTO(
            virus_name=virus_name,
            host_species=host_species,
            host_family=host_family,
            description=description,
            references=references,
        )

    @staticmethod
    def _find(norm: dict[str, str], candidates: set[str]) -> str | None:
        for c in candidates:
            if c in norm:
                return norm[c]
        return None
