"""Specificity and genetic variation check engine for PrimerForge.

Integrates mappy (minimap2) for fast pangenome alignment and implements
VariantAwareFilter to parse VCF coordinates and penalize or reject candidate
primers containing SNPs/indels in their critical 3' terminal anchor region.

Also features a pure-Python Graphical Fragment Assembly (GFA-1) parser and GFA
pangenome graph path alignment engine (Phase 3).
"""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.specificity")

# Gracefully handle mappy missing on platforms without build environments (e.g. Windows without zlib)
try:
    import mappy as mp

    MAPPY_AVAILABLE = True
except ImportError:
    mp = None
    MAPPY_AVAILABLE = False
    logger.warning(
        "mappy (minimap2 Python bindings) is not installed or could not be loaded. "
        "PrimerForge will operate with a pure-Python fallback alignment engine. "
        "For publication-grade performance and high-throughput pangenome mapping, "
        "install zlib and a C++ compiler, and rebuild mappy."
    )


@dataclass(frozen=True)
class AlignmentHit:
    """Represents a specific primer off-target or target alignment hit."""

    contig: str
    start: int
    end: int
    strand: int  # +1 for forward, -1 for reverse complement
    mismatches: int
    is_primary: bool


class PangenomeGraph:
    """GFA-1 graph representation and depth-first traversal engine."""

    def __init__(self) -> None:
        self.segments: Dict[str, str] = {}
        # adjacency: maps (node_id, orientation) -> list of (neighbor_node_id, neighbor_orientation, overlap_len)
        self.adjacency: Dict[Tuple[str, str], List[Tuple[str, str, int]]] = {}

    def add_segment(self, segment_id: str, seq: str) -> None:
        """Adds a GFA segment node and its sequence."""
        self.segments[segment_id] = seq.upper()

    def add_link(
        self, u: str, u_or: str, v: str, v_or: str, overlap_len: int = 0
    ) -> None:
        """Adds a GFA directed link transition and its reverse-complement link."""
        if (u, u_or) not in self.adjacency:
            self.adjacency[(u, u_or)] = []
        self.adjacency[(u, u_or)].append((v, v_or, overlap_len))

        # Reverse complement link: (v, comp(v_or)) -> (u, comp(u_or))
        comp = {"+": "-", "-": "+"}
        v_comp = comp[v_or]
        u_comp = comp[u_or]
        if (v, v_comp) not in self.adjacency:
            self.adjacency[(v, v_comp)] = []
        self.adjacency[(v, v_comp)].append((u, u_comp, overlap_len))

    def traverse_local_paths(
        self, max_len: int = 30
    ) -> List[Tuple[str, List[Tuple[str, str, int, int]]]]:
        """Traverses the graph starting from each node to yield sequences of length up to max_len.

        Returns:
            List of (path_sequence, path_metadata)
            where path_metadata is a list of (node_id, orientation, start_offset, end_offset) representing the layout.
        """
        paths = []
        comp_map = {"A": "T", "C": "G", "G": "C", "T": "A", "N": "N"}

        def rev_comp(seq: str) -> str:
            return "".join(comp_map.get(base, base) for base in reversed(seq.upper()))

        # To prevent exponential path explosion, limit paths per starting node/orientation to 100
        for start_node in self.segments:
            for start_or in ["+", "-"]:
                paths_from_start = 0

                def dfs(
                    curr_node: str,
                    curr_or: str,
                    curr_seq: str,
                    meta: List[Tuple[str, str, int, int]],
                    visited: Set[Tuple[str, str]],
                ) -> None:
                    nonlocal paths_from_start
                    if paths_from_start >= 100:
                        return

                    neighbors = self.adjacency.get((curr_node, curr_or), [])
                    if len(curr_seq) >= max_len or not neighbors:
                        paths.append((curr_seq[:max_len], meta))
                        paths_from_start += 1
                        return

                    for next_node, next_or, overlap in neighbors:
                        state = (next_node, next_or)
                        if state not in visited:
                            next_seg_seq = self.segments[next_node]
                            if next_or == "-":
                                next_seg_seq = rev_comp(next_seg_seq)

                            actual_overlap = min(overlap, len(next_seg_seq))
                            trimmed_next_seq = next_seg_seq[actual_overlap:]

                            next_seq = curr_seq + trimmed_next_seq
                            next_meta = meta + [
                                (
                                    next_node,
                                    next_or,
                                    len(curr_seq),
                                    len(next_seq),
                                )
                            ]

                            dfs(
                                next_node,
                                next_or,
                                next_seq,
                                next_meta,
                                visited | {state},
                            )

                seg_seq = self.segments[start_node]
                if start_or == "-":
                    seg_seq = rev_comp(seg_seq)

                dfs(
                    curr_node=start_node,
                    curr_or=start_or,
                    curr_seq=seg_seq,
                    meta=[(start_node, start_or, 0, len(seg_seq))],
                    visited={(start_node, start_or)},
                )
        return paths


class SpecificityEngine:
    """Core specificity engine handling pangenome indexing, GFA parsing, and variant filtering."""

    def __init__(self) -> None:
        """Initializes the SpecificityEngine."""
        self.aligner: Any = None
        self.fasta_path: str | None = None
        self.gfa_path: str | None = None
        self._fallback_db: Dict[str, str] = {}

        # GFA Graph-theoretic indexing parameters (Phase 3)
        self.graph = PangenomeGraph()
        self.kmer_index: Dict[str, Set[str]] = {}
        self.short_sequences: Set[str] = set()
        self.sequence_metadata: Dict[str, List[List[Tuple[str, str, int, int]]]] = {}

    def index_pangenome(self, fasta_path: str) -> None:
        """Indexes the target pangenome or reference genome.

        Supports FASTA files (.fasta, .fa) and Graphical Fragment Assembly files (.gfa).

        Args:
            fasta_path: Path to the FASTA or GFA file containing reference genomes/assembly.
        """
        if not os.path.exists(fasta_path):
            raise FileNotFoundError(f"Reference file not found at: {fasta_path}")

        # Check if the path ends with GFA
        if fasta_path.lower().endswith(".gfa"):
            self.index_gfa_pangenome(fasta_path)
            return

        self.fasta_path = fasta_path

        if MAPPY_AVAILABLE and mp is not None:
            logger.info(f"Indexing pangenome using mappy/minimap2: {fasta_path}...")
            try:
                # Use preset='sr' (short-read mode) for short primer sequences
                self.aligner = mp.Aligner(fasta_path, preset="sr")
                if not self.aligner:
                    raise RuntimeError("mappy failed to initialize Aligner.")
                logger.info("mappy pangenome index built successfully.")
            except Exception as e:
                logger.error(
                    f"mappy index compilation failed: {e}. Falling back to pure-Python."
                )
                self.aligner = None

        # Load into fallback memory database (used always if mappy fails/is absent)
        if not self.aligner:
            logger.info(
                f"Loading reference into memory for fallback alignment: {fasta_path}..."
            )
            self._load_fallback_db(fasta_path)

    def index_gfa_pangenome(self, gfa_path: str, max_len: int = 30) -> None:
        """Parses a Graphical Fragment Assembly (GFA-1) file and builds a graph path index."""
        logger.info(f"Parsing GFA pangenome graph: {gfa_path}...")
        self.gfa_path = gfa_path
        self.fasta_path = gfa_path  # For legacy API checks

        self.graph = PangenomeGraph()

        with open(gfa_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                record_type = parts[0]

                if record_type == "S":
                    # Segment: S [segment_id] [sequence]
                    if len(parts) >= 3:
                        seg_id = parts[1]
                        seq = parts[2]
                        if seq and seq != "*":
                            self.graph.add_segment(seg_id, seq)
                elif record_type == "L":
                    # Link: L [from] [from_or] [to] [to_or] [overlap_cigar]
                    if len(parts) >= 5:
                        u = parts[1]
                        u_or = parts[2]
                        v = parts[3]
                        v_or = parts[4]

                        # Parse overlap CIGAR if present
                        overlap_len = 0
                        if len(parts) >= 6:
                            cigar = parts[5].strip()
                            match = re.match(r"^(\d+)M$", cigar)
                            if match:
                                overlap_len = int(match.group(1))

                        self.graph.add_link(u, u_or, v, v_or, overlap_len)

        logger.info(
            f"Successfully parsed GFA graph with {len(self.graph.segments)} segments."
        )

        # Traverse local path segments to construct sliding-window sequence strings
        logger.info("Traversing GFA local paths up to 30bp...")
        traversed_paths = self.graph.traverse_local_paths(max_len=max_len)

        # Build k-mer seed and sequence metadata index
        self.kmer_index = {}
        self.short_sequences = set()
        self.sequence_metadata = {}

        for seq, meta in traversed_paths:
            if seq not in self.sequence_metadata:
                self.sequence_metadata[seq] = []
            self.sequence_metadata[seq].append(meta)

            if len(seq) < 6:
                self.short_sequences.add(seq)
                continue

            for i in range(len(seq) - 5):
                kmer = seq[i : i + 6]
                if kmer not in self.kmer_index:
                    self.kmer_index[kmer] = set()
                self.kmer_index[kmer].add(seq)

        logger.info(
            f"GFA sliding-window index created with {len(self.sequence_metadata)} unique paths."
        )

    def _load_fallback_db(self, fasta_path: str) -> None:
        """Loads a FASTA file into a simple in-memory key-value dictionary for fallback mapping."""
        self._fallback_db = {}
        current_header = ""
        current_seq: List[str] = []

        with open(fasta_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if current_header:
                        self._fallback_db[current_header] = "".join(current_seq)
                    current_header = line[1:].split()[0]
                    current_seq = []
                else:
                    current_seq.append(line.upper())
            if current_header:
                self._fallback_db[current_header] = "".join(current_seq)
        logger.info(f"Fallback database loaded with {len(self._fallback_db)} contigs.")

    def reverse_complement(self, seq: str) -> str:
        """Generates the reverse complement of a DNA sequence.

        Args:
            seq: Nucleotide sequence.

        Returns:
            str: Reverse complement sequence.
        """
        complement = {
            "A": "T",
            "C": "G",
            "G": "C",
            "T": "A",
            "N": "N",
            "a": "t",
            "c": "g",
            "g": "c",
            "t": "a",
            "n": "n",
        }
        return "".join(complement.get(base, base) for base in reversed(seq))

    def check_specificity(
        self, primer_sequence: str, max_mismatches: int = 3
    ) -> List[AlignmentHit]:
        """Scans the indexed reference genome/pangenome for potential primer hybridization sites.

        Args:
            primer_sequence: Primer sequence to query.
            max_mismatches: Maximum allowable mismatch threshold.

        Returns:
            List[AlignmentHit]: A list of alignment hits matching target criteria.
        """
        if not self.fasta_path and not self.gfa_path:
            raise RuntimeError(
                "Pangenome index is not loaded. Call index_pangenome first."
            )

        # Delegate to GFA alignment if active
        if self.gfa_path is not None:
            return self.check_specificity_gfa(primer_sequence, max_mismatches)

        primer_seq_upper = primer_sequence.upper()

        if MAPPY_AVAILABLE and self.aligner is not None:
            hits = []
            try:
                for hit in self.aligner.map(primer_seq_upper):
                    # Filter out very poor alignments that exceed our mismatch limit
                    if hit.NM > max_mismatches:
                        continue
                    strand = 1 if hit.strand == 1 else -1
                    hits.append(
                        AlignmentHit(
                            contig=hit.ctg,
                            start=hit.r_st,
                            end=hit.r_en,
                            strand=strand,
                            mismatches=hit.NM,
                            is_primary=hit.is_primary,
                        )
                    )
                return hits
            except Exception as e:
                logger.error(
                    f"mappy alignment failed: {e}. Running fallback alignment."
                )

        # Pure-Python sliding window fallback aligner
        return self._fallback_align(primer_seq_upper, max_mismatches)

    def check_specificity_gfa(
        self, primer_sequence: str, max_mismatches: int = 3
    ) -> List[AlignmentHit]:
        """Maps candidate primers directly to branching paths in the Graphical Fragment Assembly."""
        primer_seq = primer_sequence.upper()
        n_prim = len(primer_seq)

        # 1. Dual-strategy candidate selection:
        # If the number of unique sequences is small, scan all sequences directly for 100% sensitivity.
        # Otherwise, query the 6-mer index.
        if len(self.sequence_metadata) < 5000:
            candidates = set(self.sequence_metadata.keys())
        else:
            candidates = set()
            for i in range(n_prim - 5):
                kmer = primer_seq[i : i + 6]
                if kmer in self.kmer_index:
                    candidates.update(self.kmer_index[kmer])
            candidates.update(self.short_sequences)

        hits = []

        # 2. Slide window across each candidate graph path to check matches
        for graph_seq in candidates:
            n_graph = len(graph_seq)
            for offset in range(n_graph - n_prim + 1):
                window = graph_seq[offset : offset + n_prim]
                mismatches = sum(1 for a, b in zip(primer_seq, window) if a != b)
                if mismatches <= max_mismatches:
                    # Map offset back to GFA segment coordinates
                    metas = self.sequence_metadata[graph_seq]
                    for meta in metas:
                        for node_id, orientation, start_pos, end_pos in meta:
                            # Verify if the primer window overlaps this segment
                            if max(start_pos, offset) < min(
                                end_pos, offset + n_prim
                            ):
                                seg_len = len(self.graph.segments[node_id])
                                if orientation == "+":
                                    rel_start = offset - start_pos
                                    strand = 1
                                else:
                                    rel_start = seg_len - (
                                        offset - start_pos + n_prim
                                    )
                                    strand = -1

                                hits.append(
                                    AlignmentHit(
                                        contig=node_id,
                                        start=max(0, rel_start),
                                        end=min(seg_len, rel_start + n_prim),
                                        strand=strand,
                                        mismatches=mismatches,
                                        is_primary=True if not hits else False,
                                    )
                                )
        return hits

    def _fallback_align(self, sequence: str, max_mismatches: int) -> List[AlignmentHit]:
        """Implements a sliding-window Hamming distance alignment fallback for Windows/systems without mappy."""
        hits: List[AlignmentHit] = []
        seq_len = len(sequence)
        rev_sequence = self.reverse_complement(sequence)

        for contig, ref_seq in self._fallback_db.items():
            ref_len = len(ref_seq)
            if ref_len < seq_len:
                continue

            # Slide window across reference sequence
            for i in range(ref_len - seq_len + 1):
                window = ref_seq[i : i + seq_len]

                # Check forward strand
                mismatches_f = sum(1 for a, b in zip(sequence, window) if a != b)
                if mismatches_f <= max_mismatches:
                    hits.append(
                        AlignmentHit(
                            contig=contig,
                            start=i,
                            end=i + seq_len,
                            strand=1,
                            mismatches=mismatches_f,
                            is_primary=True if not hits else False,
                        )
                    )

                # Check reverse strand
                mismatches_r = sum(1 for a, b in zip(rev_sequence, window) if a != b)
                if mismatches_r <= max_mismatches:
                    hits.append(
                        AlignmentHit(
                            contig=contig,
                            start=i,
                            end=i + seq_len,
                            strand=-1,
                            mismatches=mismatches_r,
                            is_primary=True if not hits else False,
                        )
                    )
        return hits


class VariantAwareFilter:
    """Parses genomic variation data (VCF) and flags/penalizes primers overlapping variable positions."""

    @dataclass(frozen=True)
    class Variant:
        """Data model for parsed VCF genomic variants."""

        chrom: str
        pos: int
        ref: str
        alt: str
        maf: float

    def __init__(self) -> None:
        """Initializes the VariantAwareFilter."""
        self.variants: List[VariantAwareFilter.Variant] = []

    def load_variants(self, vcf_path: str) -> None:
        """Parses a standard VCF (or mock tab-delimited VCF) file containing variants.

        Args:
            vcf_path: Path to the VCF file.
        """
        if not os.path.exists(vcf_path):
            raise FileNotFoundError(f"VCF file not found at: {vcf_path}")

        self.variants = []
        logger.info(f"Parsing variant file: {vcf_path}...")

        with open(vcf_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) < 5:
                    continue

                chrom = parts[0]
                try:
                    pos = int(parts[1])
                except ValueError:
                    continue
                ref = parts[3]
                alt = parts[4]

                # Extract Minor Allele Frequency (MAF / AF) from INFO field
                maf = 0.0
                if len(parts) >= 8:
                    info = parts[7]
                    # Look for standard AF or MAF fields: e.g. AF=0.05 or MAF=0.02
                    maf_match = re.search(r"\b(?:AF|MAF)=([0-9.]+)\b", info)
                    if maf_match:
                        try:
                            maf = float(maf_match.group(1))
                        except ValueError:
                            maf = 0.0

                self.variants.append(
                    VariantAwareFilter.Variant(
                        chrom=chrom, pos=pos, ref=ref, alt=alt, maf=maf
                    )
                )
        logger.info(f"Loaded {len(self.variants)} genomic variants into filter memory.")

    def evaluate_primer(
        self, primer_seq: str, start_pos: int, strand: int, maf_threshold: float = 0.01
    ) -> Tuple[float, bool]:
        """Evaluates a single primer sequence against loaded variants.

        Computes a variant penalty score and checks for variants in the critical 3' end.

        Args:
            primer_seq: Sequence of the primer.
            start_pos: Start genomic coordinate of the binding site on the reference.
            strand: Strand orientation (+1 for forward, -1 for reverse complement).
            maf_threshold: Minimum Minor Allele Frequency (MAF) to trigger penalty/rejection.

        Returns:
            Tuple[float, bool]: (penalty_score, is_valid)
                penalty_score: Combined thermodynamic/kinetic mismatch penalty.
                is_valid: False if a variant falls inside the critical 3' terminal 5 bp.
        """
        primer_len = len(primer_seq)
        end_pos = start_pos + primer_len

        penalty = 0.0
        is_valid = True

        for var in self.variants:
            # Check if variant falls within primer coordinates
            if start_pos <= var.pos < end_pos:
                if var.maf < maf_threshold:
                    continue

                # Determine relative distance to the critical 3' extension end
                # Forward primer extends from start to end (3' end is at the right/high coordinate)
                # Reverse primer extends from end to start (3' end is at the left/low coordinate)
                if strand == 1:
                    dist_to_3_prime = (end_pos - 1) - var.pos
                else:
                    dist_to_3_prime = var.pos - start_pos

                # 3' Anchor violation: Any polymorphism in the last 5bp is catastrophic
                if 0 <= dist_to_3_prime <= 5:
                    logger.warning(
                        f"Critical 3' anchor violation: Variant at pos {var.pos} (MAF={var.maf}) "
                        f"is {dist_to_3_prime}bp from the 3' end on strand {strand}."
                    )
                    is_valid = False
                    penalty += 100.0  # Apply maximum penalty
                else:
                    # Non-critical overlap: Apply scalar penalty depending on proximity to 3' end
                    proximity_weight = (primer_len - dist_to_3_prime) / primer_len
                    penalty += 20.0 * proximity_weight * var.maf

        return penalty, is_valid
