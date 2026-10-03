"""
Add UPS (Ubiquitin-Proteasome System) reference data to gene browser as a new tab.
"""
import json, os

OUTDIR = os.path.dirname(__file__) + "/data"

# UPS families with IPR accessions and NCBI search links
ups_families = [
    {"family":"E1 (Ubiquitin-Activating Enzyme)","ipr":"IPR000011","pfam":"PF10585/PF09358",
     "desc":"First step of ubiquitination - ATP-dependent activation of ubiquitin",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22ubiquitin-activating+enzyme%22+OR+UBA1+OR+%22E1+ubiquitin%22)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22ubiquitin-activating+enzyme%22+OR+UBA_E1)+AND+refseq%5BFilter%5D",
     "ref":"https://pubmed.ncbi.nlm.nih.gov/37688404/"},

    {"family":"E2 (Ubiquitin-Conjugating Enzyme)","ipr":"IPR000608","pfam":"PF00179",
     "desc":"Second step - transfers ubiquitin from E1 to substrate or E3",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22ubiquitin-conjugating+enzyme%22+OR+UBC+OR+%22E2+ubiquitin%22)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22ubiquitin-conjugating+enzyme%22+OR+UBC)+AND+refseq%5BFilter%5D",
     "ref":"https://www.nature.com/articles/s41598-017-09121-4"},

    {"family":"E3 RING Finger","ipr":"IPR001841","pfam":"PF00097/PF13639/PF13920",
     "desc":"Largest E3 ligase family - RING domain mediates ubiquitin transfer to substrate",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22RING+finger%22+OR+%22RING-type+E3%22+OR+%22RING+ubiquitin+ligase%22)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22RING+finger%22+OR+%22RING-type+E3%22)+AND+refseq%5BFilter%5D",
     "ref":"https://pubmed.ncbi.nlm.nih.gov/37688404/"},

    {"family":"E3 HECT","ipr":"IPR000569","pfam":"PF00632",
     "desc":"HECT domain E3 ligases - directly catalyze ubiquitin transfer via thioester intermediate",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(HECT+OR+%22HECT+E3%22)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(HECT)+AND+refseq%5BFilter%5D",
     "ref":"https://www.nature.com/articles/s41598-021-95436-2"},

    {"family":"E3 U-box","ipr":"IPR003613","pfam":"PF04564",
     "desc":"U-box E3 ligases - modified RING domain without zinc coordination",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22U-box%22+OR+Ubox+OR+PUB)+AND+(ubiquitin+OR+E3)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22U-box%22+OR+Ubox)+AND+refseq%5BFilter%5D",
     "ref":"https://www.nature.com/articles/s41598-020-66553-1"},

    {"family":"F-box","ipr":"IPR001810","pfam":"PF00646/PF12937",
     "desc":"Substrate recognition subunit of SCF E3 ligase complex - largest plant E3 family",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22F-box%22+OR+Fbox)+AND+(ubiquitin+OR+SCF+OR+proteasome)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(%22F-box%22+OR+Fbox)+AND+refseq%5BFilter%5D",
     "ref":"https://pubmed.ncbi.nlm.nih.gov/37688404/"},

    {"family":"BTB/POZ","ipr":"IPR013069","pfam":"PF00651/PF02214",
     "desc":"BTB domain E3 ligase adaptors - substrate receptor for CUL3-based E3 ligases",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(BTB+OR+%22BTB/POZ%22)+AND+(ubiquitin+OR+CUL3)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(BTB+OR+%22BTB/POZ%22)+AND+refseq%5BFilter%5D",
     "ref":"https://pubmed.ncbi.nlm.nih.gov/37688404/"},

    {"family":"Cullin","ipr":"IPR001373","pfam":"PF00888",
     "desc":"Cullin scaffold proteins - core component of CRL (Cullin-RING Ligase) E3 complexes",
     "ncbi_gene":"https://www.ncbi.nlm.nih.gov/gene/?term=(Viridiplantae%5BOrganism%5D)+AND+(Cullin+OR+CUL1+OR+CUL3+OR+CUL4)+AND+alive%5BStatus%5D",
     "ncbi_prot":"https://www.ncbi.nlm.nih.gov/protein/?term=(Viridiplantae%5BOrganism%5D)+AND+(Cullin+OR+CUL1+OR+CUL3)+AND+refseq%5BFilter%5D",
     "ref":"https://pubmed.ncbi.nlm.nih.gov/37688404/"},
]

# Additional reference papers
ups_refs = [
    {"title":"Diversification of the ubiquitin-26S proteasome system in Brassicaceae and Poaceae","authors":"Hua Z, et al.","journal":"Int J Mol Sci","year":"2019","doi":"10.3390/ijms20133226","pmid":"","url":"https://www.mdpi.com/1422-0067/20/13/3226","desc":"UPS diversification across Brassicaceae and Poaceae - comprehensive Pfam family table"},
    {"title":"Analysis of the 20S proteasome gene family in tomato","authors":"Yan CF, Sun XM, Zhong QW, et al.","journal":"Acta Horticulturae Sinica","year":"2024","doi":"10.16420/j.issn.0513-353x.2023-0833","pmid":"","url":"https://doi.org/10.16420/j.issn.0513-353x.2023-0833","desc":"Tomato 20S proteasome gene family identification and bioinformatics"},
    {"title":"Resolving the protein ubiquitination system in plants","authors":"","journal":"Front Plant Sci","year":"2023","doi":"","pmid":"37688404","url":"https://pubmed.ncbi.nlm.nih.gov/37688404/","desc":"Comprehensive review of plant ubiquitination system including Pfam domain info"},
    {"title":"Genome-wide identification and expression analysis of E2 ubiquitin-conjugating enzymes in tomato","authors":"","journal":"Sci Rep","year":"2017","doi":"10.1038/s41598-017-09121-4","pmid":"","url":"https://www.nature.com/articles/s41598-017-09121-4","desc":"Tomato E2 ubiquitin-conjugating enzyme gene family"},
]

# Save as JSON
ups_data = {"families": ups_families, "references": ups_refs}
with open(os.path.join(OUTDIR, "ups_references.json"), "w", encoding="utf-8") as f:
    json.dump(ups_data, f, ensure_ascii=False, indent=2)

print(f"Saved {len(ups_families)} UPS families + {len(ups_refs)} references to ups_references.json")
