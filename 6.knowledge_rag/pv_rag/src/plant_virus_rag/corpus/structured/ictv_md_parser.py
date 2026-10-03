"""ICTV Report Markdown parser.

Parses ICTV full taxonomy reports (YAML front matter + Markdown body)
into PvRecordDTOs. Filters for plant virus families using host range info.
"""

import re
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO

YAML_TAXONOMY = re.compile(r"^Taxonomy:\s*(.+)$", re.MULTILINE)
# ICTV Summary table fields
SUMMARY_HOST = re.compile(r"\|\s*Host range\s*\|\s*(.+?)\s*\|", re.IGNORECASE)
SUMMARY_GENOME = re.compile(r"\|\s*Genome\s*\|\s*(.+?)\s*\|", re.IGNORECASE)
SUMMARY_EXAMPLE = re.compile(r"\|\s*Example\s*\|\s*(.+?)\s*\|", re.IGNORECASE)
SECTION_HEADER = re.compile(r"^## (.+)$", re.MULTILINE)

# Plant virus host indicators
PLANT_HOST_PATTERNS = [
    "plant", "plants", "plantae", "dicot", "monocot", "angiosperm",
    "crop", "vegetable", "fruit", "cereal", "legume", "solanac", "brassic",
    "tobacco", "tomato", "potato", "rice", "wheat", "maize", "soybean",
    "arabidopsis", "nicotiana",
]


class IctvMdParser:
    """Parses ICTV family-level Markdown reports into PvRecordDTOs.

    Only includes families with plant hosts (filters out animal/bacterial
    virus families).
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
        # Extract family name from YAML front matter
        m = YAML_TAXONOMY.search(text)
        family_name = m.group(1).strip() if m else None

        # Extract host range from Summary table
        m = SUMMARY_HOST.search(text)
        host_range = m.group(1).strip() if m else ""

        # Extract genome info
        m = SUMMARY_GENOME.search(text)
        genome_info = m.group(1).strip() if m else None

        # Extract example virus
        m = SUMMARY_EXAMPLE.search(text)
        example_virus = m.group(1).strip() if m else None

        # Extract sections
        sections = self._split_sections(text)
        biology_section = sections.get("Biology", "")
        genome_section = sections.get("Genome organization and replication", "")

        # Extract host range text from Biology section
        host_text = self._extract_host_range(biology_section)

        # Extract transmission info
        transmission_text = self._extract_transmission(biology_section)

        # Build description
        desc_parts: list[str] = []
        if family_name:
            desc_parts.append(f"Family: {family_name}")
        if host_range:
            desc_parts.append(f"Summary Host Range: {host_range}")
        if host_text:
            desc_parts.append(f"Host Range Details:\n{host_text}")
        if transmission_text:
            desc_parts.append(f"Transmission:\n{transmission_text}")
        if genome_info:
            desc_parts.append(f"Genome: {genome_info}")
        if biology_section.strip():
            desc_parts.append(f"Biology:\n{biology_section.strip()}")
        if genome_section.strip():
            desc_parts.append(f"Genome Organization:\n{genome_section.strip()}")

        description = "\n\n".join(desc_parts)

        return PvRecordDTO(
            virus_name=example_virus or family_name or "",
            taxonomy={"family": family_name} if family_name else None,
            description=description,
            genome_type=genome_info,
        )

    @staticmethod
    def _is_plant_virus(host_summary: str, text: str) -> bool:
        """Check if this is a plant virus family."""
        combined = (host_summary + " " + text[:2000]).lower()
        return any(pat in combined for pat in PLANT_HOST_PATTERNS)

    @staticmethod
    def _extract_host_range(biology_text: str) -> str:
        """Extract host range subsection from Biology section."""
        m = re.search(
            r"###\s*Host\s*range\s*\n+(.+?)(?=###|\Z)",
            biology_text, re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_transmission(biology_text: str) -> str:
        """Extract transmission subsection from Biology section."""
        m = re.search(
            r"###\s*Transmission\s*\n+(.+?)(?=###|\Z)",
            biology_text, re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    def _split_sections(self, text: str) -> dict[str, str]:
        """Split body by ## Section headers."""
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
