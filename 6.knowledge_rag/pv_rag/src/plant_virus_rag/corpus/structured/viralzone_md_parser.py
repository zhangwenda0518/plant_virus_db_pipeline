"""ViralZone Markdown parser.

Parses ViralZone genus-level Markdown files into PvRecordDTOs.
Files have a consistent structure with **HOST**, **ASSOCIATED DISEASES**,
**TRANSMISSION** fields and a taxonomy table.
"""

import re
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO

TAXONOMY_FAMILY = re.compile(r"\|\s*Family:\s*\|\s*\**(.+?)\*?\*?\s*\|")
TAXONOMY_ORDER = re.compile(r"\|\s*Order:\s*\|\s*\**(.+?)\*?\*?\s*\|")
TAXONOMY_CLASS = re.compile(r"\|\s*Class:\s*\|\s*\**(.+?)\*?\*?\s*\|")
TAXONOMY_PHYLUM = re.compile(r"\|\s*Phylum:\s*\|\s*\**(.+?)\*?\*?\s*\|")
TAXONOMY_REALM = re.compile(r"\|\s*Realm:\s*\|\s*\**(.+?)\*?\*?\s*\|")
GENUS_HEADING = re.compile(r"^# (.+?) \[", re.MULTILINE)
TAXID = re.compile(r"taxid:(\d+)")
HOST_BOLD = re.compile(r"\*\*HOST\*\*\s*\n(.+?)(?:\n\n|\Z)", re.DOTALL)
DISEASES = re.compile(r"\*\*ASSOCIATED DISEASES\*\*\s*\n(.+?)(?:\n\n|\Z)", re.DOTALL)
TRANSMISSION_BOLD = re.compile(r"\*\*TRANSMISSION\*\*\s*\n(.+?)(?:\n\n|\Z)", re.DOTALL)
SOURCE_URL = re.compile(r"^Source URL:\s*(.+)$", re.MULTILINE)


class ViralZoneMdParser:
    """Parses ViralZone Markdown genus files into PvRecordDTOs.

    Only includes genera with plant hosts.
    """

    def parse(self, file_path: Path) -> Iterator[PvRecordDTO]:
        text = file_path.read_text(encoding="utf-8")
        dto = self._parse_text(text)
        if dto:
            yield dto

    def parse_dir(self, dir_path: Path) -> Iterator[PvRecordDTO]:
        for fp in sorted(dir_path.glob("*.md")):
            yield from self.parse(fp)

    def _parse_text(self, text: str) -> PvRecordDTO | None:
        # Extract genus name
        m = GENUS_HEADING.search(text)
        genus_name = m.group(1).strip() if m else None

        # Extract taxonomy
        family = self._extract_first(TAXONOMY_FAMILY, text)
        order = self._extract_first(TAXONOMY_ORDER, text)
        class_ = self._extract_first(TAXONOMY_CLASS, text)
        phylum = self._extract_first(TAXONOMY_PHYLUM, text)
        realm = self._extract_first(TAXONOMY_REALM, text)

        # Extract host
        m = HOST_BOLD.search(text)
        host = m.group(1).strip() if m else ""

        # Extract diseases and transmission
        m = DISEASES.search(text)
        diseases = m.group(1).strip() if m else ""

        m = TRANSMISSION_BOLD.search(text)
        transmission = m.group(1).strip() if m else ""

        # Build taxonomy dict
        taxonomy: dict[str, str] = {}
        if family:
            taxonomy["family"] = family
        if order:
            taxonomy["order"] = order
        if class_:
            taxonomy["class"] = class_
        if phylum:
            taxonomy["phylum"] = phylum
        if realm:
            taxonomy["realm"] = realm

        # Build description
        desc_parts: list[str] = []
        if genus_name:
            desc_parts.append(f"Genus: {genus_name}")
        if host:
            desc_parts.append(f"**HOST**: {host}")
        if diseases:
            desc_parts.append(f"**ASSOCIATED DISEASES**: {diseases}")
        if transmission:
            desc_parts.append(f"**TRANSMISSION**: {transmission}")
        # Add genome section if present
        m = re.search(r"#### GENOME\n(.+?)(?=####|\Z)", text, re.DOTALL)
        if m:
            desc_parts.append(f"## GENOME\n{m.group(1).strip()}")

        description = "\n\n".join(desc_parts)

        return PvRecordDTO(
            virus_name=genus_name or family or "unknown",
            taxonomy=taxonomy if taxonomy else None,
            host_species=[host] if host else None,
            symptoms=[diseases] if diseases else None,
            transmission=transmission or None,
            description=description,
        )

    @staticmethod
    def _is_plant_host(host_field: str) -> bool:
        host_lower = host_field.lower()
        plant_indicators = ["plant", "plants", "crops", "crop", "vegetable"]
        animal_indicators = [
            "human", "mammal", "bird", "primate", "rodent", "fish",
            "insect", "reptile", "amphibian", "fungus", "bacteria",
            "invertebrate", "vertebrate",
        ]
        # If it explicitly says plants, include
        if any(p in host_lower for p in plant_indicators):
            return True
        # If it mentions animals but not plants, exclude
        if any(a in host_lower for a in animal_indicators):
            return False
        # Unknown — include conservatively
        return False

    @staticmethod
    def _extract_first(pattern: re.Pattern, text: str) -> str | None:
        m = pattern.search(text)
        return m.group(1).strip() if m else None
