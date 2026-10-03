"""Parse plant-insect-virus relationship data from 8.plant-insect TSV/Excel files.

Sources:
  - virus_vector_host.tsv (Supplementary Table 1.xlsx — same data)
  - wur_virus_full.tsv (WUR virus data with references)

Output: list of structured dicts for PvRecord ingestion.
"""

from __future__ import annotations

import csv
from pathlib import Path


def parse_virus_vector_host(path: Path) -> list[dict]:
    """Parse virus_vector_host.tsv (also works for Supplementary Table 1.xlsx saved as TSV)."""
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            virus_family = (row.get("Virus Family") or "").strip()
            virus_genus = (row.get("Virus Genus") or "").strip()
            virus_name = (row.get("Virus Name") or "").strip()
            vector_order = (row.get("Vector Order") or "").strip()
            vector_family = (row.get("Vector Family") or "").strip()
            vector_genus = (row.get("Vector Genus") or "").strip()
            vector_species = (row.get("Vector") or "").strip()
            host = (row.get("Virus Host") or "").strip()
            transmission = (row.get("Virus Transmission Mode") or "").strip()
            validation_doi = (row.get("DOI for Validation Virus-Insect Relationships") or "").strip()
            lineage = (row.get("Lineage") or "").strip()

            if not virus_name:
                continue

            description_parts = []
            if vector_species:
                description_parts.append(f"Vector: {vector_species}")
            if vector_family:
                description_parts.append(f"Vector family: {vector_family}")
            if vector_order:
                description_parts.append(f"Vector order: {vector_order}")
            if host:
                description_parts.append(f"Host: {host}")
            if transmission:
                description_parts.append(f"Transmission: {transmission}")
            if validation_doi:
                description_parts.append(f"Validated by: {validation_doi}")

            full_taxonomy = []
            if virus_family:
                full_taxonomy.append(virus_family)
            if virus_genus:
                full_taxonomy.append(virus_genus)

            records.append({
                "source_type": "plant_insect",
                "source_id": f"pi_{virus_name}_{vector_species}_{host}"[:80],
                "virus_name": virus_name,
                "virus_abbreviation": None,
                "taxonomy": {"family": virus_family, "genus": virus_genus, "lineage": lineage},
                "host_species": [host] if host else [],
                "vector": vector_species if vector_species else None,
                "transmission": transmission if transmission else None,
                "description": "; ".join(description_parts),
                "references": [validation_doi] if validation_doi else [],
            })
    return records


def parse_wur_virus_full(path: Path) -> list[dict]:
    """Parse wur_virus_full.tsv — WUR plant virus data with references."""
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            virus_name = (row.get("name") or "").strip()
            virus_family = (row.get("family") or "").strip()
            virus_genus = (row.get("genus") or "").strip()
            vector = (row.get("vector_org") or "").strip()
            transmission = (row.get("transmission") or "").strip()
            refs = (row.get("refs") or "").strip()

            if not virus_name:
                continue

            description_parts = []
            if vector:
                description_parts.append(f"Vector: {vector}")
            if transmission:
                description_parts.append(f"Transmission: {transmission}")
            if refs:
                # Truncate references to avoid overly long descriptions
                ref_preview = refs[:500] + "..." if len(refs) > 500 else refs
                description_parts.append(f"References: {ref_preview}")

            records.append({
                "source_type": "plant_insect",
                "source_id": f"wur_{virus_name}"[:80],
                "virus_name": virus_name,
                "virus_abbreviation": None,
                "taxonomy": {"family": virus_family, "genus": virus_genus},
                "host_species": [],
                "vector": vector if vector else None,
                "transmission": transmission if transmission else None,
                "description": "; ".join(description_parts),
                "references": [],
            })
    return records


def parse_all(
    base_dir: Path, *, include_wur: bool = True
) -> list[dict]:
    """Parse all plant-insect data files in the directory.

    Returns deduplicated records (by virus_name + vector).
    """
    records: list[dict] = []

    vh_path = base_dir / "virus_vector_host.tsv"
    if vh_path.exists():
        records.extend(parse_virus_vector_host(vh_path))

    if include_wur:
        wur_path = base_dir / "wur_virus_full.tsv"
        if wur_path.exists():
            records.extend(parse_wur_virus_full(wur_path))

    # Deduplicate by (virus_name, vector)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for r in records:
        key = (r["virus_name"], r.get("vector") or "")
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped
