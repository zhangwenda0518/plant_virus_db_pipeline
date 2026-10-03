"""Ingest plant-insect virus data into pv_records, then index into Qdrant.

Sources:
  virus_vector_host.tsv (1,376 rows)
  wur_virus_full.tsv    (1,655 rows)

Usage: python scripts/_ingest_plant_insect.py
"""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plant_virus_rag.corpus.structured.plant_insect_parser import parse_all
from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.db.models import SourceType
from plant_virus_rag.db.repositories import PvRecordRepository

# DATA_DIR defaults to project-relative; override via PLANT_INSECT_DIR env var
import os
DATA_DIR = Path(os.environ.get("PLANT_INSECT_DIR",
    Path(__file__).resolve().parent.parent.parent.parent / "8.plant-insect"))


def main():
    print(f"Parsing data from {DATA_DIR}...")
    records = parse_all(DATA_DIR)
    print(f"Parsed {len(records)} records (deduplicated)")

    new_count = 0
    update_count = 0
    with get_pv_session() as session:
        repo = PvRecordRepository(session)
        for r in records:
            try:
                result = repo.upsert(
                    source_type=SourceType.PLANT_INSECT,
                    source_id=r["source_id"],
                    virus_name=r["virus_name"],
                    virus_abbreviation=r.get("virus_abbreviation"),
                    taxonomy=r.get("taxonomy"),
                    host_species=r.get("host_species") or [],
                    host_family=None,
                    vector=r.get("vector"),
                    symptoms=[],
                    transmission=r.get("transmission"),
                    genome_type=None,
                    genome_size_kb=None,
                    description=r.get("description"),
                    references=r.get("references") or [],
                )
                if result.id:
                    new_count += 1
            except Exception:
                update_count += 1
        session.commit()
        print(f"Ingested: {new_count} new, {update_count} updated (already existed)")

    print("\nDone. Now index them into Qdrant:")
    print("  pv-ingest index --no-documents")


if __name__ == "__main__":
    main()
