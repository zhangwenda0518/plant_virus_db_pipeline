"""
PAmiRDB v3 — Experimental validation data & amiRNA design wizard.

AntiVIRmiR integration:
  Curated set of antiviral plant miRNAs inspired by AntiVIRmiR
  (https://pubmed.ncbi.nlm.nih.gov/36159991/) and primary literature on
  amiRNA-mediated virus resistance.

HONESTY NOTE (2026-10-03): the curated entries are a MIX of evidence types.
Each entry carries "experimental": True only for experimentally supported
claims; in-silico findings are marked evidence="in-silico prediction"/analysis
and entries whose reference could not be traced ("*_2025" placeholder PMIDs)
were stripped of their fake PMID and marked evidence="unverified".
Only "experimental": True entries set validated=True (the UI's "Exp. Validated").

amiRNA design wizard:
  Generates amiRNA design recommendations based on the rules from:
    - Schwab et al. (2006) Plant Cell 18:1121-1133
    - Ai et al. (2011) PLoS ONE 6:e20022
    - Carbonell et al. (2019) Curr Opin Plant Biol 47:16-23
"""
import re

# ── AntiVIRmiR curated validation set ─────────────────────────────

VALIDATED_ANTIVIRAL_MIRNAS = {
    # Format: mirna_id -> {virus, evidence, pmid, notes, experimental}
    # "experimental": True  -> experimentally supported (am iRNA/overexpression/expression)
    # "experimental": False -> in-silico or unverified (no experimental support claimed)
    "ath-miR159a": {
        "targets": ["TYLCV", "TEV"],
        "evidence": "amiRNA transgenic resistance",
        "pmid": "21304949",
        "notes": "miR159-based amiRNAs confer resistance to geminiviruses",
        "experimental": True,
    },
    "osa-miR159a": {
        "targets": ["RSV", "RBSDV"],
        "evidence": "expression correlation",
        "pmid": "33772417",
        "notes": "miR159 family broadly antiviral in monocots",
        "experimental": True,
    },
    "ath-miR408": {
        "targets": ["TYMV", "CMV"],
        "evidence": "overexpression reduces viral load",
        "pmid": "24896088",
        "notes": "Copper-regulated miRNA with broad antiviral activity",
        "experimental": True,
    },
    "osa-miR408": {
        "targets": ["RDV", "RSV"],
        "evidence": "expression + amiRNA",
        "pmid": "33772417",
        "notes": "Conserved antiviral role across monocots and dicots",
        "experimental": True,
    },
    "ghr-miR399d": {
        "targets": ["CLCuKoV-Bur"],
        "evidence": "in-silico prediction",
        "pmid": "40143327",
        "notes": "Predicted by the local SW-DP + heuristic layers (originally: 4-algorithm consensus prediction)",
        "experimental": False,
    },
    "mes-miR1446a": {
        "targets": ["ICMV-Ker"],
        "evidence": "in-silico prediction",
        "pmid": "36851701",
        "notes": "Cassava miRNA targeting ICMV by local prediction + regulatory network",
        "experimental": False,
    },
    "CA-miR838": {
        "targets": ["ChiLCV"],
        "evidence": "in-silico prediction",
        "pmid": "38656513",
        "notes": "Prediction candidate; best thermodynamic score in the local engine",
        "experimental": False,
    },
    "CA-miR2673a": {
        "targets": ["ChiLCV"],
        "evidence": "in-silico prediction",
        "pmid": "38656513",
        "notes": "Dual isoform (a/b) targeting ChiLCV (prediction)",
        "experimental": False,
    },
    "sof-miR156": {
        "targets": ["SCMV"],
        "evidence": "unverified",
        "pmid": "",  # placeholder PMID "SCMV_sugarcane_2025" removed (untraceable)
        "notes": "No traceable reference found; retained only for transparency",
        "experimental": False,
    },
    "vvi-miR399": {
        "targets": ["GVM"],
        "evidence": "in-silico prediction (unverified — no traceable reference)",
        "pmid": "",  # placeholder PMID "GVM_grapevine_2025" removed (untraceable)
        "notes": "Grapevine miRNA predicted against Grapevine virus M; reference untraceable",
        "experimental": False,
    },
    "miR168": {
        "targets": ["Potyviridae"],
        "evidence": "in-silico analysis (cross-species conservation)",
        "pmid": "33743120",
        "notes": "Conserved across 9 potyvirus hosts in 8 orders; candidate, not experimental validation",
        "experimental": False,
    },
    "miR162": {
        "targets": ["Potyviridae"],
        "evidence": "in-silico analysis (cross-species conservation)",
        "pmid": "33743120",
        "notes": "Conserved across all 15 tested plant species; core machinery candidate",
        "experimental": False,
    },
}


# ── amiRNA Design Rules ───────────────────────────────────────────

def amiRNA_design_rules():
    """Return the amiRNA design rules from literature."""
    return {
        "critical_positions": {
            "3-6": "Mismatches at these positions lead to failure of amiRNA-mediated resistance",
            "9": "Critical for cleavage; mismatch here abolishes silencing",
            "10-11": "A/U preferred at these positions for efficient silencing",
            "12": "Critical position for target recognition",
            "2,10,11,13,15,18": "Intermediate importance for silencing efficacy",
        },
        "design_checklist": [
            "1. Seed region (2-8): PERFECT complementarity to target",
            "2. Positions 10-11: Prefer A/U with compulsory binding",
            "3. Total mismatches <= 4 (excluding seed)",
            "4. No more than 2 consecutive mismatches in positions 13-21",
            "5. Free energy <= -20 kcal/mol",
            "6. Query coverage >= 18 nucleotides",
            "7. Identity > 80%",
            "8. Use endogenous miRNA backbone (e.g., ath-MIR319a)",
            "9. Replace mature miRNA with 21-nt amiRNA sequence",
            "10. Verify amiRNA* (passenger strand) has mismatches at 5' end",
        ],
        "backbone_recommendations": [
            {"name": "ath-MIR319a", "use": "Most widely used; high expression in dicots"},
            {"name": "osa-MIR528", "use": "Preferred for monocot expression"},
            {"name": "ath-MIR390a", "use": "Alternative dicot backbone"},
        ],
    }


def score_amiRNA_candidate(mirna_seq: str, target_region: str,
                            check_positions: list = None) -> dict:
    """
    Score a candidate amiRNA sequence against design rules.
    Returns a score (0-100) and detailed feedback.
    """
    from alignment import align_mirna_to_target
    
    score = 100
    feedback = []
    
    # Run miRanda alignment
    result = align_mirna_to_target("candidate", mirna_seq, "target", target_region)
    if result is None:
        return {"score": 0, "feedback": ["No valid alignment found"]}
    
    # Check seed region
    if not result.seed_perfect:
        score -= 40
        feedback.append("FAIL: Seed region (2-8) not perfectly complementary")
    else:
        feedback.append("PASS: Seed region perfect")
    
    # Check mismatches
    if result.num_mismatches > 4:
        score -= 30
        feedback.append(f"FAIL: Too many mismatches ({result.num_mismatches} > 4)")
    else:
        feedback.append(f"PASS: Mismatches within limit ({result.num_mismatches})")
    
    # Check energy
    if result.energy > -20:
        score -= 20
        feedback.append(f"FAIL: Energy too high ({result.energy:.1f} > -20)")
    else:
        feedback.append(f"PASS: Energy acceptable ({result.energy:.1f})")
    
    # Check identity
    if result.identity < 80:
        score -= 10
        feedback.append(f"FAIL: Identity too low ({result.identity:.1f}% < 80%)")
    else:
        feedback.append(f"PASS: Identity sufficient ({result.identity:.1f}%)")
    
    # Check A/U at positions 10-11
    if len(mirna_seq) >= 11:
        au_ok = mirna_seq[9].upper() in 'AU' and mirna_seq[10].upper() in 'AU'
        if not au_ok:
            score -= 5
            feedback.append(f"WARN: Positions 10-11 should be A/U (got {mirna_seq[9]}{mirna_seq[10]})")
    
    # Check position binding
    if check_positions:
        pb = result.position_binding
        for pos in check_positions:
            if pb.get(pos) not in ('WC', 'wobble'):
                score -= 5
                feedback.append(f"WARN: Position {pos} not paired")
    
    return {
        "score": max(0, score),
        "feedback": feedback,
        "alignment": result.alignment_str,
        "energy": result.energy,
        "identity": result.identity,
        "recommendation": (
            "Strong candidate for amiRNA design" if score >= 80 else
            "Acceptable with minor modifications" if score >= 60 else
            "Needs significant redesign"
        ),
    }


# ── AntiVIRmiR 4-Sub-Database Model (paper 4) ────────────────────

ANTIVIRMIR_SUBDB = {
    "DEmiRVIR": {
        "description": "Differentially expressed host/virus miRNAs",
        "total_entries": 10033,
        "viruses": 21,
        "fields": ["id", "virus", "taxonomy", "miRNA_name", "sequence",
                   "expression_change", "organism", "cell_line",
                   "experimental_method", "score", "pmid"],
    },
    "AntiVmiR": {
        "description": "Antiviral host miRNAs with validated targets",
        "total_entries": 1642,
        "viruses": 34,
        "fields": ["id", "virus", "taxonomy", "miRNA_name", "target_gene",
                   "uniprot_id", "target_organism", "target_process",
                   "cell_line", "experimental_method", "target_region", "pmid"],
    },
    "VIRmiRNA2": {
        "description": "Experimentally validated viral miRNAs + isomiRs",
        "total_entries": 3340,
        "viruses": 50,
        "fields": ["id", "virus", "miRNA_name", "sequence", "is_miR_variants",
                   "experimental_method", "pmid"],
    },
    "VIRmiRTar2": {
        "description": "Experimentally validated viral miRNA targets",
        "total_entries": 7726,
        "viruses": 21,
        "fields": ["id", "virus", "miRNA_name", "target_gene", "target_organism",
                   "validation_method", "pmid"],
    },
}

# ── psRNATarget Standard Parameters (paper 2, 5) ──────────────────

PSRNATARGET_PARAMS = {
    "expectation_cutoff": 4.0,      # paper: 0-2.0 strict, 4.0-5.0 broad
    "max_upe": 25.0,                # unpaired energy
    "hsp_size": 19,                 # complementarity scoring length
    "seed_region": "2-13",          # extended seed
    "seed_mismatches_max": 2,
    "total_mismatches_max": 4,
    "gu_penalty": 0.5,
    "other_mismatch_penalty": 1.0,
    "flank_upstream": 17,
    "flank_downstream": 13,
    "translation_inhibition_range": "9-11",
}


# ── miRNA family extraction / matching ────────────────────────────

_MIRNA_RE = re.compile(r'miR(\d+)', re.IGNORECASE)


def extract_family(mirna_id: str) -> str:
    """Extract the family key from an miRNA ID (e.g. 'ath-miR159a' -> 'miR159').

    2026-10-03 fix: the previous logic (`mid.split('-')[1]` then
    `.replace('a','').replace('b','')`) did substring surgery, so 'miR1599'
    matched the 'miR159' entry. The family is the miR number with the trailing
    isoform letter dropped, compared on numeric boundaries only.
    """
    if not mirna_id:
        return ''
    m = _MIRNA_RE.search(mirna_id)
    return f"miR{m.group(1)}" if m else mirna_id.strip()


def _family_number(name: str):
    m = _MIRNA_RE.search(name or '')
    return m.group(1) if m else None


def get_validation_status(mirna_family: str) -> dict:
    """
    Check if a miRNA family has an entry in the curated anti-viral set.
    Matching is by exact miR number (numeric boundary): 'miR1599' does NOT
    match 'miR159'.  Only entries flagged experimental=True are returned with
    validated=True; in-silico / unverified entries return validated=False but
    expose their evidence and (when traceable) the PMID.
    """
    qnum = _family_number(mirna_family) or _family_number(extract_family(mirna_family))

    for mir_id, data in VALIDATED_ANTIVIRAL_MIRNAS.items():
        enum = _family_number(mir_id)
        if qnum and enum and qnum == enum:
            return {
                "validated": bool(data.get("experimental", False)),
                "reference_mirna": mir_id,
                "targets": data["targets"],
                "evidence": data["evidence"],
                "pmid": data["pmid"],
                "notes": data["notes"],
            }
    
    return {"validated": False}


if __name__ == '__main__':
    # Test amiRNA scoring
    result = score_amiRNA_candidate(
        "UUUGGAUUGAAGGGAGCUCUA",  # ath-miR159a
        "UAAACCUAACUUCCCUCGAGAU",  # complementary target
    )
    print(f"AmiRNA Score: {result['score']}/100")
    print(f"Recommendation: {result['recommendation']}")
    for fb in result['feedback']:
        print(f"  {fb}")
    
    # Test validation lookup
    for fam in ['miR159', 'miR408', 'miR156', 'miR999']:
        status = get_validation_status(fam)
        print(f"\n{ fam}: validated={status['validated']}", end='')
        if status['validated']:
            print(f" ({status['evidence']}, PMID:{status['pmid']})")
