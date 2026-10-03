"""
PAmiRDB v7 — Host-filtered pipeline.
Only tests miRNA-virus pairs where the virus is known to infect that plant species.

Matches virus hosts to miRNA species using 4-level strategy:
  1. Exact match (normalized)
  2. Host is substring of miRNA species
  3. miRNA species is substring of host
  4. Genus-level match (first word)

Usage:
  python scripts/pipeline_v7_host_filtered.py
  python scripts/pipeline_v7_host_filtered.py --fast       # Fast mode (3 core algorithms)
  python scripts/pipeline_v7_host_filtered.py --workers 8  # Parallel mode
"""

from __future__ import annotations
import json, sys, time, os
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent))

from consensus import run_consensus_prediction, to_dict

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "predictions_v7.json"
SEQ_MAX_LEN = 15000

# 2026-10-03: silent truncation at SEQ_MAX_LEN dropped the tail of large virus
# genomes from the alignment. Truncation is now logged per virus and summarised
# into data/truncated_viruses.tsv (91 viruses expected at SEQ_MAX_LEN=15000).
_TRUNCATED = {}  # virus_id -> (original_len, used_len)


def _truncate_logged(vid, vseq):
    """Truncate vseq to SEQ_MAX_LEN, warning once per virus."""
    if len(vseq) > SEQ_MAX_LEN:
        if vid not in _TRUNCATED:
            _TRUNCATED[vid] = (len(vseq), SEQ_MAX_LEN)
            print(f"  [WARN] {vid}: {len(vseq):,} nt > SEQ_MAX_LEN={SEQ_MAX_LEN}; "
                  f"alignment limited to first {SEQ_MAX_LEN:,} nt", flush=True)
        return vseq[:SEQ_MAX_LEN]
    return vseq


def write_truncation_report():
    if not _TRUNCATED:
        return
    path = DATA_DIR / "truncated_viruses.tsv"
    with open(path, 'w') as f:
        f.write("virus_id\toriginal_length\tused_length\n")
        for vid, (orig, used) in sorted(_TRUNCATED.items()):
            f.write(f"{vid}\t{orig}\t{used}\n")
    print(f"  Truncated viruses: {len(_TRUNCATED)} -> {path}")


def _process_pair(t):
    """Process one miRNA-virus pair. Module-level for pickle compatibility."""
    mid, mseq, vid, vname, vfam, vseq, fast = t
    if len(vseq) < 21:
        return None
    cr = run_consensus_prediction(mid, mseq, vid, vname, vfam, vseq, fast_mode=fast)
    if cr is None or not cr.passes_pamirdb_filter:
        return None
    return to_dict(cr)


def normalize(name: str) -> str:
    return name.strip().lower().replace(' ', '_').replace('-', '_')


def match_host_to_species(host_raw: str, mirna_species_list: list[tuple[str, str]]) -> str | None:
    """Match a virus host name to a miRNA species name. Returns matched species or None."""
    h = normalize(host_raw)
    if not h or len(h) < 2:
        return None

    # 1. Exact match
    for mn, ms in mirna_species_list:
        if h == mn:
            return ms

    # 2. Host is substring of miRNA species (host "capsicum" → "Capsicum_annuum")
    if len(h) >= 4:
        for mn, ms in mirna_species_list:
            if h in mn:
                return ms

    # 3. miRNA species is substring of host (host "prunus_persica_f_compressa" → "Prunus_persica")
    for mn, ms in mirna_species_list:
        if mn in h and len(mn) >= 6:
            return ms

    # 4. Genus-level match (host "Capsicum sp." → "Capsicum_annuum")
    h_genus = h.split('_')[0]
    if len(h_genus) >= 4:
        for mn, ms in mirna_species_list:
            m_genus = mn.split('_')[0]
            if h_genus == m_genus:
                return ms

    return None


def build_host_filter():
    """Build the host-filtered pair index: {species_name: set(mirna_ids)}"""
    print("=" * 60)
    print("  Building Host-Filtered Pair Index")
    print("=" * 60)

    # Load data
    with open(DATA_DIR / "mirna" / "plant_mirnas_full.json") as f:
        mirnas = json.load(f)
    print(f"  miRNAs: {len(mirnas)}")

    with open(DATA_DIR / "virus_genomes" / "viruses_full.json") as f:
        viruses = json.load(f)
    print(f"  Viruses (meta): {len(viruses)}")

    # Load virus sequences
    virus_seqs = {}
    fa_path = DATA_DIR / "virus_genomes" / "viruses_full.fasta"
    if fa_path.exists():
        cid, cseq = None, []
        for line in open(fa_path):
            line = line.strip()
            if line.startswith('>'):
                if cid:
                    virus_seqs[cid] = ''.join(cseq)
                cid = line[1:].split('|')[0].split()[0]
                cseq = []
            else:
                cseq.append(line)
        if cid:
            virus_seqs[cid] = ''.join(cseq)
    print(f"  Virus sequences: {len(virus_seqs)}")

    # Build miRNA species index
    mirna_by_species = defaultdict(list)
    for mid, info in mirnas.items():
        mirna_by_species[info['species_name']].append((mid, info))

    mirna_species_list = [(normalize(s), s) for s in mirna_by_species.keys()]
    print(f"  miRNA species: {len(mirna_species_list)}")

    # Match viruses to miRNA species
    pairs = []  # [(mirna_id, mirna_seq, virus_id, virus_meta)]
    virus_matched = set()
    species_stats = Counter()

    for vid, vmeta in viruses.items():
        if vid not in virus_seqs or len(virus_seqs[vid]) < 21:
            continue
        # Support both 'hosts' (list, new format) and 'host' (string, old format)
        hosts_raw = vmeta.get('hosts', [vmeta.get('host', '')])
        if isinstance(hosts_raw, str):
            hosts_raw = [hosts_raw]
        matched_species_set = set()
        for host in hosts_raw:
            ms = match_host_to_species(host, mirna_species_list)
            if ms and ms in mirna_by_species:
                matched_species_set.add(ms)
        if matched_species_set:
            virus_matched.add(vid)
            vmeta_copy = dict(vmeta)
            vmeta_copy['_seq'] = virus_seqs[vid]
            for ms in matched_species_set:
                species_stats[ms] += 1
                vmeta_copy['_mirna_sp'] = ms
                vmeta_copy['_mirna_sp_name'] = ms
                for mid, minfo in mirna_by_species[ms]:
                    pairs.append((mid, minfo['sequence'], vid, vmeta_copy))

    print(f"  Viruses matched to host: {len(virus_matched)}")
    print(f"  Species with host match: {len(species_stats)}")
    print(f"  Total miRNA-virus pairs: {len(pairs):,}")

    # Also include unmatched viruses but only check their known host species
    unmatched = [vid for vid in viruses if vid not in virus_matched and vid in virus_seqs]
    if unmatched:
        print(f"  Unmatched viruses (no host filter): {len(unmatched)}")

    return pairs, mirnas, virus_seqs


def run_single(pairs, fast_mode=True):
    """Run prediction for the filtered pairs (single-threaded)."""
    print(f"\n{'=' * 60}")
    print(f"  Running Predictions ({len(pairs):,} pairs)")
    print(f"  Mode: {'fast' if fast_mode else 'full (slower local heuristics enabled)'}")
    print(f"{'=' * 60}")

    results = []
    t0 = time.time()

    for i, (mid, mseq, vid, vmeta) in enumerate(pairs):
        vseq = _truncate_logged(vid, vmeta.get('_seq', ''))
        vname = vmeta.get('name', vid)
        vfam = vmeta.get('family', 'unknown')

        if i > 0 and i % 5000 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(pairs) - i) / rate
            print(f"  [{i:,}/{len(pairs):,}] {rate:.0f} pairs/s hits={len(results)} ETA={eta/60:.0f}min")

        cr = run_consensus_prediction(mid, mseq, vid, vname, vfam, vseq, fast_mode=fast_mode)
        if cr is None or not cr.passes_pamirdb_filter:
            continue

        entry = to_dict(cr)
        # Load full miRNA info
        entry['mirna_species'] = vmeta.get('_mirna_sp', '')
        entry['mirna_species_name'] = vmeta.get('_mirna_sp_name', '')
        entry['target_protein'] = ''
        entry['matching_status'] = ''
        results.append(entry)

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f} min ({len(results)} hits)")
    return results, elapsed


def run_parallel(pairs, num_workers=None, fast_mode=True):
    """Run prediction in parallel with multiprocessing.

    fast_mode is propagated to every worker task (2026-10-03: --full was
    silently ignored on the parallel path, which always ran fast_mode=True).
    """
    from multiprocessing import Pool, cpu_count
    import itertools

    nw = num_workers or max(1, cpu_count() - 4)
    print(f"\n{'=' * 60}")
    print(f"  Running Predictions — Parallel ({nw} workers)")
    print(f"  Mode: {'fast' if fast_mode else 'full'}")
    print(f"  Pairs: {len(pairs):,}")
    print(f"{'=' * 60}")

    # Pre-process: extract seq from meta, make tuples serializable
    tasks = []
    for mid, mseq, vid, vmeta in pairs:
        vseq = _truncate_logged(vid, vmeta.get('_seq', ''))
        tasks.append((mid, mseq, vid,
                      vmeta.get('name', vid),
                      vmeta.get('family', 'unknown'),
                      vseq, fast_mode))

    t0 = time.time()

    results_raw = []
    with Pool(processes=nw) as pool:
        for i, r in enumerate(pool.imap_unordered(_process_pair, tasks, chunksize=100)):
            if r is not None:
                results_raw.append(r)
            if (i + 1) % 10000 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(tasks) - i - 1) / rate
                print(f"  [{i+1:,}/{len(tasks):,}] {rate:.0f} p/s hits={len(results_raw)} ETA={eta/60:.0f}min")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f} min ({len(results_raw)} hits)")
    return results_raw, elapsed


def save_and_summarize(results, elapsed, total_pairs):
    """Save results and print summary."""
    # Stats
    stats = Counter()
    for r in results:
        stats[r.get('consensus_level', 'LOW')] += 1

    output = {
        "version": "v7-host-filtered",
        "total_pairs": total_pairs,
        "total_predictions": len(results),
        "runtime_minutes": round(elapsed / 60, 1),
        "summary": {"consensus_levels": dict(stats)},
        "results": results,
    }

    # Atomic write: temp file + rename, so a crashed run never leaves a
    # truncated predictions_v7.json behind (run_v7.sh cleans up *.tmp).
    tmp_path = Path(str(OUTPUT_FILE) + ".tmp")
    with open(tmp_path, 'w') as f:
        json.dump(output, f, indent=2)
    os.replace(tmp_path, OUTPUT_FILE)

    print(f"\n{'=' * 60}")
    print(f"  v7 Results: {len(results)} predictions ({total_pairs:,} pairs)")
    for level in ['VERY HIGH', 'HIGH+', 'HIGH', 'MEDIUM+', 'MEDIUM', 'LOW+', 'LOW']:
        cnt = stats.get(level, 0)
        if cnt:
            print(f"    {level:10s}: {cnt:5d}  {'#' * min(cnt // 2, 80)}")
    print(f"  Output: {OUTPUT_FILE}")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='PAmiRDB v7 — Host-Filtered Pipeline')
    p.add_argument('--fast', action='store_true', default=True,
                   help='Fast mode (3 core algorithms) [default]')
    p.add_argument('--full', action='store_true',
                   help='Full 8-algorithm mode (slower)')
    p.add_argument('--workers', type=int, default=None,
                   help='Number of parallel workers (default: cpu_count-4)')
    p.add_argument('--serial', action='store_true',
                   help='Force single-threaded mode')
    p.add_argument('--pairs-only', action='store_true',
                   help='Only build pair index, show stats, exit')
    args = p.parse_args()

    fast_mode = not args.full

    # Build host filter
    pairs, mirnas, virus_seqs = build_host_filter()

    if args.pairs_only:
        print("\n  Pair index built. Exiting (--pairs-only).")
        sys.exit(0)

    if not pairs:
        print("\n  ERROR: No pairs to process!")
        sys.exit(1)

    # Run
    if args.serial or args.workers == 1:
        results, elapsed = run_single(pairs, fast_mode=fast_mode)
    elif args.workers:
        results, elapsed = run_parallel(pairs, num_workers=args.workers, fast_mode=fast_mode)
    else:
        # Use parallel by default if cpu_count > 4
        from multiprocessing import cpu_count
        if cpu_count() > 4:
            results, elapsed = run_parallel(pairs, fast_mode=fast_mode)
        else:
            results, elapsed = run_single(pairs, fast_mode=fast_mode)

    save_and_summarize(results, elapsed, len(pairs))
    write_truncation_report()
