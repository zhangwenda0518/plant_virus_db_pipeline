# Plant EVE Landscape — `/eve/`

Kingdom-scale survey of **endogenous viral elements (EVEs)** in plant genomes.
It presents the results of a fresh genome-wide sweep of 1,527 plant genomes. It is
**not** the same analysis as the former `/te/` TE & EVE database (curated TE /
LTR-retrotransposon / RNA-virome reference collections), which was **retired on
2026-09-23** because transposable elements are unrelated to plant viruses;
`/te/` now 301-redirects here.

**Live**: http://39.106.101.94/eve/

---

## 1. What the numbers mean (read this before quoting anything)

| Quantity | Value | Notes |
|---|---:|---|
| Plant genomes screened | **1,527** | `plantGIR` genome packages |
| Genomes carrying ≥1 EVE | **1,400** | of the 1,527 screened — the chip in the page header shows **this** number, not 1,527 |
| Host families with ≥1 EVE | **284** | of 295 families in `plantGIR` |
| `viral_supported` loci, **raw** | **205,873** | = tier1 201,782 + tier2 4,091 — matches `CONCLUSION.md` |
| **phiX174 contamination removed** | **55,737** (27%) | one assembly, `Abies_alba_v1.0`, carries 55,725 of them |
| `viral_supported` loci, **decontaminated** | **150,136** | = tier1 146,045 + tier2 4,091 — **what this page shows** |
| DNA : RNA (identified families) | **29.3 : 1** | Caulimoviridae 36,781 vs all RNA families 1,323 |
| RT-domain tree tips | 269 | 250 EVE (83 host families) + 19 reference viruses |

> **Two totals exist and both are correct.** `CONCLUSION.md` reports 205,873 —
> the raw sweep total, before decontamination. This page shows **150,136**,
> i.e. the same set after the phiX174 spike-in was removed locus-by-locus and
> the contaminated assembly excluded genome-wide. The difference (55,737) is
> not missing data, it is removed contamination. The page states both numbers
> in the header/footer so a reader can never confuse them.

**Loci ≠ viruses.** Every count is an *integration site*. 93,226 loci
(`Other_viral`) resolved no further than "virus" inside RVDB, and 16,836
(`Phage`) are bacterial-virus-like. Of the **40,074** loci that fall in an
identifiable virus family, Caulimoviridae alone is 36,781 (92%).

## 2. Pipeline (upstream, not part of this page)

| Stage | Method | Library |
|---|---|---|
| 1 discover | seqkit 50 kb windows + `diamond blastx --fast -F 15` | NCBI virus RefSeq proteins (722,738) |
| 2 two-sided verdict | locus vs plant+virus hybrid library; viral bitscore must beat plant bitscore | UniRef50 plants+virus (4,982,985) |
| 3 annotate | `diamond` LCA direct classification (`--outfmt 102`) | RVDB v31 (771,606, taxonomy embedded) |
| 4 decontaminate | phiX174 hit removal (locus-level + genome-level) | — |
| 5 nr rescue (tier2) | `diamond blastx` vs local nr; plant-virus hits with bs ≥ 50 promoted | nr |

Downstream analyses used on this page: host-family rarefaction, past-vs-present
quadrants, 95 %-identity clustering for copy number, bitscore percentile
calibration, Pfam `RVT_1` extraction → MAFFT/clipkit/IQ-TREE, and per-case
ORF/flank export. All scripts live on the analysis server (`~/eve_kingdom/`).

## 3. Files

```
docs/eve/
├── index.html              # the page (ECharts, 8 perspectives, EN/ZH)
├── echarts.min.js          # local copy — never a CDN (project rule)
├── data/
│   ├── eve_landscape.json  # overview, virus taxa, host families, DNA/RNA, matrices
│   ├── eve_dynamics.json   # past-vs-present, amplification, per-genome scatter, rarefied, thresholds
│   ├── eve_phylo.json      # Newick tree, nearest-reference calls, cases, viroids, phiX QC
│   └── _audit/*.tsv        # human-checkable mirrors of every headline number
├── build_eve_data.py       # aggregation script (runs on the analysis server)
└── work/
    ├── check_eve_ui.py     # headless smoke test: 8 perspectives + control probes
    ├── check_eve_i18n.py   # EN/ZH toggle test
    └── snap_extra.py       # extra sub-mode screenshots
```

## 4. Rebuilding the data

`build_eve_data.py` runs **on the analysis server** (it reads `~/eve_kingdom/`
and `/home/train/plantGIR/`), then the JSON is copied back:

```bash
ssh success "python3 -" < docs/eve/build_eve_data.py     # writes ~/eve_kingdom/web_json/
scp success:"~/eve_kingdom/web_json/*.json"        docs/eve/data/
scp success:"~/eve_kingdom/web_json/_audit/*.tsv"  docs/eve/data/_audit/
```

Key implementation notes (also in the script header):

* The 773 MB / 28.5 M-row loci master table is reduced by **one awk pass** to
  the 205,873 `viral_supported` rows; python never loads the full table.
* **tier2 (4,091 loci) is not in the master table.** `updated_tier2_log.tsv`
  must be merged in or the total silently falls to 146,045.
* Genome type (dsDNA-RT / ssDNA / dsDNA / dsRNA / ssRNA+ / ssRNA−) is an
  explicit table — do not infer it from family names.
* Host family comes from the `plantGIR` directory layout; plant group
  (algae → eudicot) is the mode of the species' phylum/class/order.

## 5. Verification

The same suite runs against **both** the local dev server and the live site —
the base URL is read from the `EVE_BASE` environment variable:

```bash
# local (needs: python -m http.server 8899 running in docs/)
C:/Python312/python.exe docs/eve/work/check_eve_ui.py   .tmp/
C:/Python312/python.exe docs/eve/work/check_eve_i18n.py .tmp/

# live
EVE_BASE=http://39.106.101.94/eve/index.html \
  C:/Python312/python.exe docs/eve/work/check_eve_ui.py   .tmp/live/
EVE_BASE=http://39.106.101.94/eve/index.html \
  C:/Python312/python.exe docs/eve/work/check_eve_i18n.py .tmp/live/
```

All four runs must end with `0 checks failed`. The UI test asserts, per perspective,
that the canvas is non-blank and that every control (perspective buttons,
genome-type and host-group checkboxes, Top-N, PNG, CSV, Reset) actually
produces its side effect — not merely that the page does not crash.

## 6. Deployment

17 files, deployed **one at a time** (never `scp -r` a directory that already
exists on the server — it would roll back newer live content), each verified by
md5 against the local copy. Pre-existing files were backed up first as
`*.bak_20260923.eve*`.

```bash
R=/opt/plant_virus_db/plant_virus_db_pipeline
scp docs/eve/index.html        root@39.106.101.94:$R/docs/eve/
scp docs/eve/echarts.min.js    root@39.106.101.94:$R/docs/eve/
scp docs/eve/README.md         root@39.106.101.94:$R/docs/eve/
scp docs/eve/build_eve_data.py root@39.106.101.94:$R/docs/eve/
scp docs/eve/data/eve_*.json   root@39.106.101.94:$R/docs/eve/data/
scp docs/eve/data/_audit/*.tsv root@39.106.101.94:$R/docs/eve/data/_audit/
scp docs/eve/work/*.py         root@39.106.101.94:$R/docs/eve/work/
scp docs/index.html docs/README.md root@39.106.101.94:$R/docs/
```

nginx (`/etc/nginx/conf.d/plant-virus.conf`) — **`root`, not `alias`**:

```nginx
location /eve/ {
    root /opt/plant_virus_db/plant_virus_db_pipeline/docs;   # note: root does NOT include /eve/
    index index.html;
    try_files $uri $uri/ =404;
    expires 10m;
}
```

Same shape as `/phylo/molecular/`, and used in preference to the `alias` form
because the page fetches `data/*.json` and `data/_audit/*.tsv` from a
subdirectory — `root` is the form already proven on this server
(`/phylo/molecular/families/family_index.json` → 200 JSON). (The `alias` form
does in fact serve subdirectory *files* correctly here —
`/association/associations.json` → 200 — but `root` costs nothing extra and
avoids the directory-index edge case entirely.)

Verify:

```bash
curl -o /dev/null -w '%{http_code}\n' http://39.106.101.94/eve/                        # 200
curl -o /dev/null -w '%{http_code}\n' http://39.106.101.94/eve/data/eve_landscape.json  # 200
C:/Python312/python.exe deploy/check_site_routes.py                                    # 缺口数 = 0
```

…then md5-compare every deployed file against the local copy.
