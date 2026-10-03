"""
Extended virus data with gene/protein annotations.

Each virus now includes gene coordinates and protein product names,
enabling PAmiRDB to report:
  - Which viral protein is targeted
  - Whether binding is Withinmatch or Overlapping
"""

VIRUS_GENES = {
    "TYLCV-IR": {
        "name": "Tomato yellow leaf curl virus - Iran",
        "accession": "NC_004005.1",
        "family": "geminiviridae",
        "genome_length": 2774,
        "genes": [
            {"gene": "V1", "protein": "Coat protein (CP)", "start": 307, "end": 1077},
            {"gene": "V2", "protein": "Movement protein (MP)", "start": 136, "end": 495},
            {"gene": "C1", "protein": "Replication-associated protein (Rep)", "start": 1530, "end": 2606},
            {"gene": "C2", "protein": "Transcriptional activator (TrAP)", "start": 1215, "end": 1619},
            {"gene": "C3", "protein": "Replication enhancer (REn)", "start": 1065, "end": 1466},
            {"gene": "C4", "protein": "C4 protein", "start": 2159, "end": 2452},
        ],
    },
    "ACMV": {
        "name": "African cassava mosaic virus",
        "accession": "NC_001467.2",
        "family": "geminiviridae",
        "genome_length": 2779,
        "genes": [
            {"gene": "AV1", "protein": "Coat protein (CP)", "start": 294, "end": 1064},
            {"gene": "AV2", "protein": "Movement protein (MP)", "start": 133, "end": 486},
            {"gene": "AC1", "protein": "Replication-associated protein (Rep)", "start": 1519, "end": 2595},
            {"gene": "AC2", "protein": "Transcriptional activator (TrAP)", "start": 1208, "end": 1609},
            {"gene": "AC3", "protein": "Replication enhancer (REn)", "start": 1063, "end": 1461},
            {"gene": "AC4", "protein": "AC4 protein", "start": 2147, "end": 2446},
        ],
    },
    "BGMV": {
        "name": "Bean golden mosaic virus",
        "accession": "NC_004042.1",
        "family": "geminiviridae",
        "genome_length": 2646,
        "genes": [
            {"gene": "AV1", "protein": "Coat protein (CP)", "start": 312, "end": 1067},
            {"gene": "AC1", "protein": "Replication-associated protein (Rep)", "start": 1464, "end": 2525},
            {"gene": "AC2", "protein": "Transcriptional activator (TrAP)", "start": 1173, "end": 1568},
            {"gene": "AC3", "protein": "Replication enhancer (REn)", "start": 1039, "end": 1437},
            {"gene": "AC4", "protein": "AC4 protein", "start": 2112, "end": 2411},
        ],
    },
    "MYMV": {
        "name": "Mungbean yellow mosaic virus",
        "accession": "NC_001932.1",
        "family": "geminiviridae",
        "genome_length": 2725,
        "genes": [
            {"gene": "AV1", "protein": "Coat protein (CP)", "start": 327, "end": 1097},
            {"gene": "AV2", "protein": "Movement protein (MP)", "start": 151, "end": 510},
            {"gene": "AC1", "protein": "Replication-associated protein (Rep)", "start": 1539, "end": 2603},
            {"gene": "AC2", "protein": "Transcriptional activator (TrAP)", "start": 1216, "end": 1617},
            {"gene": "AC3", "protein": "Replication enhancer (REn)", "start": 1083, "end": 1481},
        ],
    },
    "WDV": {
        "name": "Wheat dwarf virus",
        "accession": "NC_003326.1",
        "family": "geminiviridae",
        "genome_length": 2749,
        "genes": [
            {"gene": "MP", "protein": "Movement protein", "start": 1, "end": 374},
            {"gene": "CP", "protein": "Coat protein", "start": 354, "end": 1052},
            {"gene": "RepA", "protein": "Replication-associated protein A", "start": 1235, "end": 2158},
            {"gene": "Rep", "protein": "Replication-associated protein", "start": 1472, "end": 2479},
        ],
    },
    "PVY": {
        "name": "Potato virus Y",
        "accession": "NC_001616.1",
        "family": "potyviridae",
        "genome_length": 9704,
        "genes": [
            {"gene": "P1", "protein": "P1 proteinase", "start": 184, "end": 984},
            {"gene": "HC-Pro", "protein": "Helper component proteinase", "start": 985, "end": 2343},
            {"gene": "P3", "protein": "P3 protein", "start": 2344, "end": 3462},
            {"gene": "6K1", "protein": "6K1 protein", "start": 3463, "end": 3618},
            {"gene": "CI", "protein": "Cylindrical inclusion protein", "start": 3619, "end": 5520},
            {"gene": "6K2", "protein": "6K2 protein", "start": 5521, "end": 5676},
            {"gene": "VPg", "protein": "Genome-linked protein VPg", "start": 5677, "end": 6249},
            {"gene": "NIa-Pro", "protein": "Nuclear inclusion a proteinase", "start": 6250, "end": 6978},
            {"gene": "NIb", "protein": "Nuclear inclusion b (RNA polymerase)", "start": 6979, "end": 8529},
            {"gene": "CP", "protein": "Coat protein", "start": 8530, "end": 9330},
        ],
    },
    "TEV": {
        "name": "Tobacco etch virus",
        "accession": "NC_001555.1",
        "family": "potyviridae",
        "genome_length": 9494,
        "genes": [
            {"gene": "P1", "protein": "P1 proteinase", "start": 144, "end": 1010},
            {"gene": "HC-Pro", "protein": "Helper component proteinase", "start": 1011, "end": 2375},
            {"gene": "P3", "protein": "P3 protein", "start": 2376, "end": 3464},
            {"gene": "6K1", "protein": "6K1 protein", "start": 3465, "end": 3620},
            {"gene": "CI", "protein": "Cylindrical inclusion protein", "start": 3621, "end": 5522},
            {"gene": "6K2", "protein": "6K2 protein", "start": 5523, "end": 5681},
            {"gene": "VPg", "protein": "Genome-linked protein VPg", "start": 5682, "end": 6251},
            {"gene": "NIa-Pro", "protein": "Nuclear inclusion a proteinase", "start": 6252, "end": 6980},
            {"gene": "NIb", "protein": "Nuclear inclusion b (RNA polymerase)", "start": 6981, "end": 8519},
            {"gene": "CP", "protein": "Coat protein", "start": 8520, "end": 9353},
        ],
    },
    "SMV": {
        "name": "Soybean mosaic virus",
        "accession": "NC_002634.1",
        "family": "potyviridae",
        "genome_length": 9588,
        "genes": [
            {"gene": "P1", "protein": "P1 proteinase", "start": 132, "end": 992},
            {"gene": "HC-Pro", "protein": "Helper component proteinase", "start": 993, "end": 2360},
            {"gene": "P3", "protein": "P3 protein", "start": 2361, "end": 3455},
            {"gene": "6K1", "protein": "6K1 protein", "start": 3456, "end": 3614},
            {"gene": "CI", "protein": "Cylindrical inclusion protein", "start": 3615, "end": 5516},
            {"gene": "6K2", "protein": "6K2 protein", "start": 5517, "end": 5675},
            {"gene": "VPg", "protein": "Genome-linked protein VPg", "start": 5676, "end": 6245},
            {"gene": "NIa-Pro", "protein": "Nuclear inclusion a proteinase", "start": 6246, "end": 6974},
            {"gene": "NIb", "protein": "Nuclear inclusion b (RNA polymerase)", "start": 6975, "end": 8513},
            {"gene": "CP", "protein": "Coat protein", "start": 8514, "end": 9344},
        ],
    },
    "PPV": {
        "name": "Plum pox virus",
        "accession": "NC_001445.1",
        "family": "potyviridae",
        "genome_length": 9741,
        "genes": [
            {"gene": "P1", "protein": "P1 proteinase", "start": 147, "end": 1028},
            {"gene": "HC-Pro", "protein": "Helper component proteinase", "start": 1029, "end": 2408},
            {"gene": "P3", "protein": "P3 protein", "start": 2409, "end": 3497},
            {"gene": "6K1", "protein": "6K1 protein", "start": 3498, "end": 3653},
            {"gene": "CI", "protein": "Cylindrical inclusion protein", "start": 3654, "end": 5555},
            {"gene": "6K2", "protein": "6K2 protein", "start": 5556, "end": 5714},
            {"gene": "VPg", "protein": "Genome-linked protein VPg", "start": 5715, "end": 6284},
            {"gene": "NIa-Pro", "protein": "Nuclear inclusion a proteinase", "start": 6285, "end": 7013},
            {"gene": "NIb", "protein": "Nuclear inclusion b (RNA polymerase)", "start": 7014, "end": 8576},
            {"gene": "CP", "protein": "Coat protein", "start": 8577, "end": 9371},
        ],
    },
    "TuMV": {
        "name": "Turnip mosaic virus",
        "accession": "NC_002509.1",
        "family": "potyviridae",
        "genome_length": 9833,
        "genes": [
            {"gene": "P1", "protein": "P1 proteinase", "start": 130, "end": 1122},
            {"gene": "HC-Pro", "protein": "Helper component proteinase", "start": 1123, "end": 2490},
            {"gene": "P3", "protein": "P3 protein", "start": 2491, "end": 3570},
            {"gene": "6K1", "protein": "6K1 protein", "start": 3571, "end": 3726},
            {"gene": "CI", "protein": "Cylindrical inclusion protein", "start": 3727, "end": 5628},
            {"gene": "6K2", "protein": "6K2 protein", "start": 5629, "end": 5787},
            {"gene": "VPg", "protein": "Genome-linked protein VPg", "start": 5788, "end": 6357},
            {"gene": "NIa-Pro", "protein": "Nuclear inclusion a proteinase", "start": 6358, "end": 7086},
            {"gene": "NIb", "protein": "Nuclear inclusion b (RNA polymerase)", "start": 7087, "end": 8646},
            {"gene": "CP", "protein": "Coat protein", "start": 8647, "end": 9507},
        ],
    },
}


def get_target_gene(virus_id, align_start, align_end, virus_family="", genome_length=0):
    """Determine which gene(s) a miRNA targets and matching status."""
    virus = VIRUS_GENES.get(virus_id)

    # Fallback: generic potyvirus gene model (~10KB genome)
    if not virus and virus_family == "potyviridae" and genome_length > 8000:
        virus = _build_potyvirus_model(virus_id, genome_length)

    if not virus:
        return "Unknown", "Unknown"

    genes = virus.get("genes", [])
    hit_genes = []

    for g in genes:
        # Check if alignment overlaps with gene
        if align_end > g["start"] and align_start < g["end"]:
            hit_genes.append(f'{g["gene"]}:{g["protein"]}')

    if len(hit_genes) == 0:
        return "Intergenic", "Outside gene"
    elif len(hit_genes) == 1:
        return hit_genes[0], "Withinmatch"
    else:
        return " / ".join(hit_genes), "Overlapping"


def _build_potyvirus_model(virus_name: str, genome_len: int) -> dict:
    """Build generic potyvirus gene model using proportional coordinates.

    Potyvirus genome organization (approximate % positions):
      P1:     0-8%    HC-Pro: 8-24%   P3:    24-36%
      6K1:   36-38%   CI:    38-57%   6K2:   57-59%
      VPg:   59-64%   NIa:   64-72%   NIb:   72-88%
      CP:    88-97%
    """
    # Proportional gene boundaries for a typical 10KB potyvirus
    gene_template = [
        ("P1",    0.00, 0.08, "P1 proteinase"),
        ("HC-Pro", 0.08, 0.24, "Helper component proteinase"),
        ("P3",     0.24, 0.36, "P3 protein"),
        ("6K1",    0.36, 0.38, "6K1 protein"),
        ("CI",     0.38, 0.57, "Cylindrical inclusion protein"),
        ("6K2",    0.57, 0.59, "6K2 protein"),
        ("VPg",    0.59, 0.64, "Genome-linked protein VPg"),
        ("NIa-Pro", 0.64, 0.72, "Nuclear inclusion a proteinase"),
        ("NIb",    0.72, 0.88, "Nuclear inclusion b (RNA polymerase)"),
        ("CP",     0.88, 0.97, "Coat protein"),
    ]

    genes = []
    for gene_name, start_frac, end_frac, protein_desc in gene_template:
        genes.append({
            "gene": gene_name,
            "protein": protein_desc,
            "start": int(start_frac * genome_len),
            "end": int(end_frac * genome_len),
        })

    return {
        "name": virus_name,
        "family": "potyviridae",
        "genome_length": genome_len,
        "genes": genes,
    }


def export_virus_data():
    """Export extended virus data as JSON for the database."""
    import json
    return json.dumps(VIRUS_GENES, indent=2)
