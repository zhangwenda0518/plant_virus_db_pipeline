"""NCBI final.cluster.ref_info.tsv parser.

Parses the NCBI Virus database TSV export, filters for plant viruses
(those with non-empty VMR_Family), and aggregates by VMR_Species while
preserving all unique accessions, hosts, and geo locations.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from plant_virus_rag.corpus.structured.ictv_parser import PvRecordDTO


class NcbiTsvParser:
    """Parses NCBI final.cluster.ref_info.tsv into PvRecordDTOs.

    Filters for rows with VMR taxonomy (plant viruses), aggregates by
    VMR_Species. Preserves all unique accessions, hosts, geo locations
    and molecule types per species.
    """

    def parse(self, file_path: Path) -> Iterator[PvRecordDTO]:
        seen_species: dict[str, dict] = {}  # vm_species -> aggregated data
        with open(file_path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                vm_family = (row.get("VMR_Family") or "").strip()
                vm_species = (row.get("VMR_Species") or "").strip()

                if not vm_family or not vm_species:
                    continue

                acc = (row.get("Accession") or "").strip()
                species_ictv = (row.get("Species_ICTV") or "").strip()
                host = (row.get("Host") or "").strip()
                geo = (row.get("Geo_Location") or "").strip()
                genbank_title = (row.get("GenBank_Title") or "").strip()
                mol_type = (row.get("Molecule_type") or "").strip()
                segment = (row.get("Segment") or "").strip()
                vm_genus = (row.get("VMR_Genus") or "").strip()
                length = (row.get("Length") or "").strip()

                if vm_species in seen_species:
                    agg = seen_species[vm_species]
                    if acc and acc not in agg["accessions"]:
                        agg["accessions"].append(acc)
                    if host and host not in agg["hosts"]:
                        agg["hosts"].append(host)
                    if geo and geo not in agg["geo_locations"]:
                        agg["geo_locations"].append(geo)
                    if mol_type and mol_type not in agg["mol_types"]:
                        agg["mol_types"].append(mol_type)
                    if segment and segment not in agg["segments"]:
                        agg["segments"].append(segment)
                    if genbank_title and not agg["genbank_title"]:
                        agg["genbank_title"] = genbank_title
                    # Update virus name to the most specific
                    if species_ictv and not agg["species_ictv"]:
                        agg["species_ictv"] = species_ictv
                    continue

                seen_species[vm_species] = {
                    "family": vm_family,
                    "genus": vm_genus,
                    "species_ictv": species_ictv,
                    "accessions": [acc] if acc else [],
                    "hosts": [host] if host else [],
                    "geo_locations": [geo] if geo else [],
                    "mol_types": [mol_type] if mol_type else [],
                    "segments": [segment] if segment else [],
                    "genbank_title": genbank_title,
                    "length": length,
                }

        for vm_species, agg in seen_species.items():
            virus_name = agg["species_ictv"] or vm_species

            # Build description
            desc_parts = [f"Species: {virus_name}"]
            if agg["family"]:
                desc_parts.append(f"Family: {agg['family']}")
            if agg["genus"]:
                desc_parts.append(f"Genus: {agg['genus']}")
            if agg["accessions"]:
                desc_parts.append(f"Accessions ({len(agg['accessions'])}): {', '.join(agg['accessions'][:20])}")
            if agg["hosts"]:
                desc_parts.append(f"Hosts: {', '.join(agg['hosts'])}")
            if agg["geo_locations"]:
                desc_parts.append(f"Locations: {', '.join(agg['geo_locations'][:10])}")
            if agg["mol_types"]:
                desc_parts.append(f"Molecule types: {', '.join(agg['mol_types'])}")
            if agg["segments"]:
                desc_parts.append(f"Segments: {', '.join(agg['segments'])}")
            if agg["genbank_title"]:
                desc_parts.append(f"Description: {agg['genbank_title']}")

            yield PvRecordDTO(
                virus_name=virus_name,
                taxonomy={
                    "family": agg["family"],
                    "genus": agg["genus"],
                } if agg["family"] else None,
                host_species=agg["hosts"] if agg["hosts"] else None,
                genome_type=agg["mol_types"][0] if agg["mol_types"] else None,
                description="\n".join(desc_parts),
                references=agg["accessions"] if agg["accessions"] else None,
            )
