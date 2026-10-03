"""
Build reference database for gene browser.
"""
import json, os

OUTDIR = os.path.dirname(__file__) + "/data"

refs = [
    # NLR references
    {"id":"NLR001","title":"RefPlantNLR: a comprehensive collection of experimentally validated plant NLR immune receptors",
     "authors":"Kourelis J, Sakai T, Adachi H, Kamoun S","journal":"bioRxiv","year":"2020",
     "doi":"10.1101/2020.07.08.193961","url":"https://www.biorxiv.org/content/10.1101/2020.07.08.193961v2",
     "category":"NLR","desc":"442 experimentally validated NLRs from 11 orders, 31 genera"},

    {"id":"NLR002","title":"PRGdb 4.0: an updated database dedicated to genes involved in plant disease resistance",
     "authors":"Calle Garcia J, Guadagno A, Paytuvi-Gallart A, et al.","journal":"Nucleic Acids Res","year":"2022",
     "doi":"10.1093/nar/gkab1087","pmid":"34791468","url":"https://pubmed.ncbi.nlm.nih.gov/34791468/",
     "category":"NLR","desc":"586,652 putative resistance genes across 182 proteomes"},

    {"id":"NLR003","title":"PlantNLRatlas: a comprehensive dataset of full- and partial-length NLR resistance genes across 100 chromosome-level plant genomes",
     "authors":"Li J, Yang J, Wang Y, et al.","journal":"Front Plant Sci","year":"2023",
     "doi":"10.3389/fpls.2023.1178069","url":"https://www.frontiersin.org/articles/10.3389/fpls.2023.1178069/full",
     "category":"NLR","desc":"68,452 NLR genes from 100 plant genomes, 15 sub-groups"},

    # sRNA pathway references
    {"id":"sRNA001","title":"Phylogenetic analyses of seven protein families refine the evolution of small RNA pathways in green plants",
     "authors":"Belanger S, Zhan J, Meyers BC","journal":"Plant Physiol","year":"2023",
     "doi":"10.1093/plphys/kiad141","pmid":"36861327","url":"https://pubmed.ncbi.nlm.nih.gov/36861327/",
     "category":"sRNA","desc":"AGO/DCL/RDR/DRB/SGS3/SE/HEN1 - 196 species, comprehensive phylogeny"},

    {"id":"sRNA002","title":"Antiviral RNAi in plants: from DCL/RDR to diverse viral counter-defense strategies",
     "authors":"Guo Z, Li Y, Ding SW","journal":"Viruses","year":"2025",
     "doi":"10.3390/v18020184","url":"https://pubmed.ncbi.nlm.nih.gov/41134097/",
     "category":"sRNA","desc":"DCLs/RDRs core antiviral RNAi - vsiRNA biogenesis and amplification"},

    {"id":"sRNA003","title":"Small RNA-mediated plant-virus interactions and applications in plant virus defense",
     "authors":"Zhao JH, Guo HS","journal":"Int J Mol Sci","year":"2022",
     "doi":"10.3390/ijms23020696","pmid":"35054890","url":"https://pubmed.ncbi.nlm.nih.gov/35054890/",
     "category":"sRNA","desc":"AGO/DCL/RDR in plant-virus interactions - comprehensive review"},

    # AGO-specific validation papers
    {"id":"AGO001","title":"Arabidopsis ARGONAUTE1 is an miRNA-guided endonuclease that cleaves target mRNA",
     "authors":"Baumberger N, Baulcombe DC","journal":"Proc Natl Acad Sci USA","year":"2005",
     "doi":"10.1073/pnas.0509193102","pmid":"16141451","url":"https://pubmed.ncbi.nlm.nih.gov/16141451/",
     "category":"AGO","desc":"AGO1 = primary miRNA effector with slicer activity"},

    {"id":"AGO002","title":"ARGONAUTE4 is required for RNA-directed DNA methylation in Arabidopsis",
     "authors":"Zilberman D, Cao X, Jacobsen SE","journal":"Science","year":"2003",
     "doi":"10.1126/science.1079695","pmid":"12408866","url":"https://pubmed.ncbi.nlm.nih.gov/12408866/",
     "category":"AGO","desc":"AGO4 mediates RdDM - 24-nt siRNA-guided DNA methylation"},

    {"id":"AGO003","title":"Sorting of small RNAs into Arabidopsis argonaute complexes depends on 5-prime terminal nucleotide",
     "authors":"Mi S, Cai T, Hu Y, et al.","journal":"Cell","year":"2008",
     "doi":"10.1016/j.cell.2008.02.034","pmid":"18345015","url":"https://pubmed.ncbi.nlm.nih.gov/18345015/",
     "category":"AGO","desc":"AGO-sRNA sorting rules - 5-prime nt identity determines AGO loading"},

    {"id":"AGO004","title":"ARGONAUTE2 mediates antiviral RNA silencing in Arabidopsis",
     "authors":"Wang XB, Jovel J, Udomporn P, et al.","journal":"Plant Cell","year":"2011",
     "doi":"10.1105/tpc.111.088096","pmid":"22043420","url":"https://pubmed.ncbi.nlm.nih.gov/22043420/",
     "category":"AGO","desc":"AGO2 - major antiviral Argonaute in Arabidopsis"},

    # DCL-specific
    {"id":"DCL001","title":"Four plant Dicers mediate viral small RNA biogenesis and DNA virus induced silencing",
     "authors":"Blevins T, Rajeswaran R, Pooggin MM","journal":"Nucleic Acids Res","year":"2006",
     "doi":"10.1093/nar/gkl886","pmid":"17093917","url":"https://pubmed.ncbi.nlm.nih.gov/17093917/",
     "category":"DCL","desc":"DCL2/3/4 produce virus-derived siRNAs"},

    {"id":"DCL002","title":"Hierarchical action and inhibition of plant Dicer-like proteins in antiviral defense",
     "authors":"Deleris A, Gallego-Bartolome J, Bao J, et al.","journal":"Science","year":"2006",
     "doi":"10.1126/science.1128214","pmid":"16825590","url":"https://pubmed.ncbi.nlm.nih.gov/16825590/",
     "category":"DCL","desc":"DCL4>DCL2 hierarchical antiviral function"},

    # RDR-specific
    {"id":"RDR001","title":"An RNA-dependent RNA polymerase gene in Arabidopsis is required for posttranscriptional gene silencing mediated by a transgene but not by a virus",
     "authors":"Dalmay T, Hamilton A, Rudd S, et al.","journal":"Cell","year":"2000",
     "doi":"10.1016/S0092-8674(00)80864-8","pmid":"10847686","url":"https://pubmed.ncbi.nlm.nih.gov/10847686/",
     "category":"RDR","desc":"RDR6 (SDE1) - essential for transgene PTGS"},

    {"id":"RDR002","title":"RNA-dependent RNA polymerase 1 from Nicotiana tabacum confers resistance to Tobacco mosaic virus",
     "authors":"Yang SJ, Carter SA, Cole AB, et al.","journal":"Proc Natl Acad Sci USA","year":"2004",
     "doi":"10.1073/pnas.0305681101","pmid":"15051864","url":"https://pubmed.ncbi.nlm.nih.gov/15051864/",
     "category":"RDR","desc":"RDR1 - direct antiviral activity, virus resistance"},

    # DRB-specific
    {"id":"DRB001","title":"HYL1 controls the microRNA-mediated gene silencing pathway in Arabidopsis",
     "authors":"Han MH, Goud S, Song L, Fedoroff N","journal":"Proc Natl Acad Sci USA","year":"2004",
     "doi":"10.1073/pnas.0306940101","pmid":"14726527","url":"https://pubmed.ncbi.nlm.nih.gov/14726527/",
     "category":"DRB","desc":"HYL1 (DRB1) - essential miRNA biogenesis cofactor"},

    # SGS3
    {"id":"SGS3001","title":"SGS3 and SGS2/SDE1/RDR6 are required for juvenile development and the production of trans-acting siRNAs in Arabidopsis",
     "authors":"Peragine A, Yoshikawa M, Wu G, et al.","journal":"Genes Dev","year":"2004",
     "doi":"10.1101/gad.1231804","pmid":"15371305","url":"https://pubmed.ncbi.nlm.nih.gov/15371305/",
     "category":"SGS3","desc":"SGS3 + RDR6 = tasiRNA biogenesis"},

    # HEN1
    {"id":"HEN1001","title":"HEN1 is a double-stranded RNA binding protein that catalyzes 2-prime-O-methylation of small RNAs",
     "authors":"Park W, Li J, Song R, et al.","journal":"Curr Biol","year":"2002",
     "doi":"10.1016/S0960-9822(02)00819-5","pmid":"12007421","url":"https://pubmed.ncbi.nlm.nih.gov/12007421/",
     "category":"HEN1","desc":"HEN1 - sRNA 3-prime terminal 2-O-methylation, protects from degradation"},
]

with open(os.path.join(OUTDIR, "gene_references.json"), "w", encoding="utf-8") as f:
    json.dump(refs, f, ensure_ascii=False, indent=2)

print(f"Saved {len(refs)} references to gene_references.json")
categories = {}
for r in refs:
    cat = r["category"]
    categories[cat] = categories.get(cat, 0) + 1
for cat, cnt in sorted(categories.items()):
    print(f"  {cat}: {cnt} refs")
