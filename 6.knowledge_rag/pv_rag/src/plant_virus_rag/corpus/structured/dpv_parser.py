"""DPV (Descriptions of Plant Viruses) Markdown parser.

Parses DPV database .md files into PvRecordDTOs. DPV files have a
highly consistent structure with header metadata (Family/Genus/Species)
followed by standardised sections (Host Range, Transmission, etc.).
"""

import re
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO

SECTION_HEADER = re.compile(r"^### (.+)$", re.MULTILINE)
HOST_SPECIES_PAT = re.compile(r"\*([^*]+)\*")  # italic scientific names
FAMILY_LINE = re.compile(r"^##### Family:\s*(.+)$", re.MULTILINE)
GENUS_LINE = re.compile(r"^##### Genus:\s*(.+)$", re.MULTILINE)
SPECIES_LINE = re.compile(r"^##### Species:\s*(.+)$", re.MULTILINE)
DPV_LINE = re.compile(r"^### DPV NO:\s*(.+)$", re.MULTILINE)


class DpvParser:
    """Parses DPV Markdown files into PvRecordDTOs."""

    def parse(self, file_path: Path) -> Iterator[PvRecordDTO]:
        text = file_path.read_text(encoding="utf-8")
        dto = self._parse_text(text)
        if dto:
            yield dto

    def parse_dir(self, dir_path: Path) -> Iterator[PvRecordDTO]:
        for fp in sorted(dir_path.glob("*.md")):
            yield from self.parse(fp)

    def _parse_text(self, text: str) -> PvRecordDTO | None:
        family = self._extract_first(FAMILY_LINE, text)
        genus = self._extract_first(GENUS_LINE, text)
        species_raw = self._extract_first(SPECIES_LINE, text)
        dpv_no = self._extract_first(DPV_LINE, text)

        if not species_raw and not genus:
            return None

        virus_name, acronym = self._parse_species(species_raw or "")
        if not virus_name:
            # Fall back to heading
            m = re.search(r"^# (.+)$", text, re.MULTILINE)
            virus_name = m.group(1).strip() if m else (genus or "unknown")

        # Build taxonomy
        taxonomy: dict[str, str] = {}
        if family:
            taxonomy["family"] = family
        if genus:
            taxonomy["genus"] = genus

        # Extract key sections
        sections = self._split_sections(text)
        host_section = sections.get("Host Range and Symptomatology", "")
        transmission_section = sections.get("Transmission by Vectors", "")
        diseases_section = sections.get("Main Diseases", "")
        genome_section = sections.get("Genome Properties", "")
        geo_section = sections.get("Geographical Distribution", "")

        # Extract host species (italic scientific names) from host section
        host_species = HOST_SPECIES_PAT.findall(host_section)
        host_species = [h.strip() for h in host_species if len(h.strip()) > 2]

        # Build structured description
        desc_parts: list[str] = []
        if dpv_no:
            desc_parts.append(f"DPV No: {dpv_no}")
        if diseases_section.strip():
            desc_parts.append(f"## Main Diseases\n{diseases_section.strip()}")
        if host_section.strip():
            desc_parts.append(f"## Host Range and Symptomatology\n{host_section.strip()}")
        if transmission_section.strip():
            desc_parts.append(f"## Transmission by Vectors\n{transmission_section.strip()}")
        if genome_section.strip():
            desc_parts.append(f"## Genome Properties\n{genome_section.strip()}")
        if geo_section.strip():
            desc_parts.append(f"## Geographical Distribution\n{geo_section.strip()}")

        description = "\n\n".join(desc_parts)

        return PvRecordDTO(
            virus_name=virus_name,
            virus_abbreviation=acronym,
            taxonomy=taxonomy if taxonomy else None,
            host_species=host_species if host_species else None,
            genome_type=None,
            symptoms=None,  # DPV has this in text form, not structured lists
            description=description,
        )

    @staticmethod
    def _extract_first(pattern: re.Pattern, text: str) -> str | None:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _parse_species(raw: str) -> tuple[str, str | None]:
        """Parse 'Species: Tomato spotted wilt virus | Acronym: TSWV'"""
        parts = raw.split("|")
        virus_name = parts[0].strip()
        acronym: str | None = None
        for p in parts[1:]:
            m = re.search(r"Acronym:\s*(.+)", p.strip())
            if m:
                acronym = m.group(1).strip()
        return virus_name, acronym

    def _split_sections(self, text: str) -> dict[str, str]:
        """Split DPV body by ### Section headers."""
        sections: dict[str, str] = {}
        current_name = "preamble"
        current_text: list[str] = []

        for line in text.split("\n"):
            m = SECTION_HEADER.match(line)
            if m:
                if current_text:
                    sections[current_name] = "\n".join(current_text).strip()
                current_name = m.group(1).strip()
                current_text = []
            else:
                current_text.append(line)
        if current_text:
            sections[current_name] = "\n".join(current_text).strip()
        return sections
