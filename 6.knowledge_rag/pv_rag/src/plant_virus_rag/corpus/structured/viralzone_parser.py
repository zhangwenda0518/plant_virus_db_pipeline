"""ViralZone fact-sheet parser.

ViralZone provides structured fact-sheets per virus family/genus with fields
like host, transmission, symptoms, genome type. This parser handles CSV or
tab-delimited exports of ViralZone data.

Expected columns (subset used):
  - Virus name / Family / Genus
  - Host(s)
  - Transmission (vector, mechanical, seed, etc.)
  - Symptoms / Disease
  - Genome type
  - Genome size (kb)
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO


class ViralZoneParser:
    """Parses ViralZone structured data into PvRecordDTOs."""

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
            {"virus name", "virus_name", "name", "family", "genus", "species"},
        )
        if not virus_name:
            return None

        abbreviation = self._find(norm, {"abbreviation", "acronym", "short name"})

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

        host_str = self._find(norm, {"host", "hosts", "host_species", "host species"})
        host_species: list[str] | None = None
        host_family: str | None = None
        if host_str:
            parts = [h.strip() for h in host_str.replace(";", ",").split(",") if h.strip()]
            if parts:
                host_species = parts

        host_family_str = self._find(norm, {"host family", "host_family"})
        if host_family_str:
            host_family = host_family_str

        vector = self._find(norm, {"vector", "transmission", "transmission vector", "transmission_vector"})

        symptoms_str = self._find(norm, {"symptoms", "disease", "diseases", "symptom"})
        symptoms: list[str] | None = None
        if symptoms_str:
            symptoms = [s.strip() for s in symptoms_str.replace(";", ",").split(",") if s.strip()]

        transmission = self._find(
            norm, {"transmission mode", "transmission_mode", "transmission", "mode"}
        )

        genome_type = self._find(
            norm, {"genome type", "genome_type", "genome composition", "genome", "nucleic acid"}
        )

        genome_size_kb: float | None = None
        gs_str = self._find(norm, {"genome size (kb)", "genome_size_kb", "genome size", "genome_size", "size (kb)"})
        if gs_str:
            try:
                genome_size_kb = float(gs_str.replace("~", "").replace("kb", "").strip())
            except ValueError:
                pass

        # Build description from remaining fields
        description_parts: list[str] = []
        for k, v in norm.items():
            if len(v) > 3 and k not in {
                "virus name", "virus_name", "name", "family", "genus", "abbreviation",
                "acronym", "short name", "order", "host", "hosts", "host_species",
                "host species", "host family", "host_family", "vector", "transmission",
                "symptoms", "disease", "diseases", "genome type", "genome_type",
                "genome composition", "genome", "nucleic acid", "genome size (kb)",
                "genome_size_kb", "genome size", "genome_size", "size (kb)",
                "transmission mode", "transmission_mode", "mode",
            }:
                description_parts.append(f"{k}: {v}")
        description = "\n".join(description_parts) if description_parts else None

        return PvRecordDTO(
            virus_name=virus_name,
            virus_abbreviation=abbreviation,
            taxonomy=taxonomy,
            host_species=host_species,
            host_family=host_family,
            vector=vector,
            symptoms=symptoms,
            transmission=transmission,
            genome_type=genome_type,
            genome_size_kb=genome_size_kb,
            description=description,
        )

    @staticmethod
    def _find(norm: dict[str, str], candidates: set[str]) -> str | None:
        for c in candidates:
            if c in norm:
                return norm[c]
        return None
