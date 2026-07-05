"""Biophysical engine for PrimerForge wrapping primer3-py.

Provides thermodynamic calculations, primer sequence verification, and candidate primer
pair generation using classic nearest-neighbor thermodynamic parameters.
"""

from dataclasses import dataclass
from typing import Any, Dict, List
import primer3

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.biophysics")


@dataclass(frozen=True)
class PrimerSequence:
    """Represents a single primer sequence with calculated biophysical properties."""

    sequence: str
    start: int
    length: int
    tm: float
    gc_percent: float
    hairpin_dg: float  # Free energy (kcal/mol) of the most stable self-hairpin
    homodimer_dg: float  # Free energy (kcal/mol) of the most stable homodimer
    penalty: float


@dataclass(frozen=True)
class PrimerPair:
    """Represents an assembled forward and reverse primer pair with joint biophysical properties."""

    forward: PrimerSequence
    reverse: PrimerSequence
    product_size: int
    cross_dimer_dg: float  # Free energy (kcal/mol) of the most stable heterodimer
    penalty: float


class BiophysicsEngine:
    """Core biophysical engine wrapping primer3-py for thermodynamic primer design."""

    def __init__(
        self,
        opt_tm: float = 60.0,
        min_tm: float = 57.0,
        max_tm: float = 63.0,
        opt_size: int = 20,
        min_size: int = 18,
        max_size: int = 24,
        salt_monovalent: float = 50.0,
        salt_divalent: float = 1.5,
        dntp_conc: float = 0.6,
    ) -> None:
        """Initializes the BiophysicsEngine with global design parameters.

        Args:
            opt_tm: Optimal melting temperature in Celsius.
            min_tm: Minimum allowed melting temperature in Celsius.
            max_tm: Maximum allowed melting temperature in Celsius.
            opt_size: Optimal primer length in nucleotides.
            min_size: Minimum allowed primer length in nucleotides.
            max_size: Maximum allowed primer length in nucleotides.
            salt_monovalent: Monovalent salt concentration in mM (default 50.0).
            salt_divalent: Divalent salt concentration in mM (default 1.5).
            dntp_conc: dNTP concentration in mM (default 0.6).
        """
        self.opt_tm = opt_tm
        self.min_tm = min_tm
        self.max_tm = max_tm
        self.opt_size = opt_size
        self.min_size = min_size
        self.max_size = max_size
        self.salt_monovalent = salt_monovalent
        self.salt_divalent = salt_divalent
        self.dntp_conc = dntp_conc

        logger.debug("BiophysicsEngine initialized with parameters:")
        logger.debug(
            f"Tm: opt={opt_tm}, min={min_tm}, max={max_tm} | "
            f"Size: opt={opt_size}, min={min_size}, max={max_size}"
        )

    def calculate_thermo_features(self, sequence: str) -> Dict[str, float]:
        """Calculates single sequence thermodynamic features using primer3 parameters.

        Calculates melting temperature (Tm), self-hairpin free energy change (dG),
        and homodimer free energy change (dG).

        Args:
            sequence: Nucleotide sequence (5' to 3').

        Returns:
            Dict[str, float]: Calculated thermodynamic properties.
        """
        # DNA sanitization
        seq_clean = "".join(c for c in sequence.upper() if c in "ATGC")
        if not seq_clean:
            return {
                "tm": 0.0,
                "hairpin_dg": 0.0,
                "homodimer_dg": 0.0,
            }
        sequence = seq_clean

        # Calculate melting temperature
        tm = primer3.calc_tm(sequence)

        # Calculate self-hairpin stability
        # primer3 returns a structure where .dg represents delta G in cal/mol. We convert to kcal/mol.
        hairpin_res = primer3.calc_hairpin(sequence)
        hairpin_dg = hairpin_res.dg / 1000.0 if hasattr(hairpin_res, "dg") else 0.0

        # Calculate homodimer stability
        homodimer_res = primer3.calc_homodimer(sequence)
        homodimer_dg = (
            homodimer_res.dg / 1000.0 if hasattr(homodimer_res, "dg") else 0.0
        )

        return {
            "tm": tm,
            "hairpin_dg": hairpin_dg,
            "homodimer_dg": homodimer_dg,
        }

    def calculate_heterodimer_dg(self, seq1: str, seq2: str) -> float:
        """Calculates the cross-dimer (heterodimer) free energy between two sequences.

        Args:
            seq1: First nucleotide sequence (5' to 3').
            seq2: Second nucleotide sequence (5' to 3').

        Returns:
            float: Free energy (dG) of heterodimerization in kcal/mol.
        """
        s1 = "".join(c for c in seq1.upper() if c in "ATGC")
        s2 = "".join(c for c in seq2.upper() if c in "ATGC")
        if not s1 or not s2:
            return 0.0
        seq1, seq2 = s1, s2
        heterodimer_res = primer3.calc_heterodimer(seq1, seq2)
        return heterodimer_res.dg / 1000.0 if hasattr(heterodimer_res, "dg") else 0.0

    def calculate_terminal_dg(
        self,
        sequence: str,
        n_terminal: int = 5,
        temperature_c: float = 37.0,
    ) -> float:
        """Computes the 3'-terminal free energy using SantaLucia 1998 NN parameters.

        Implements the unified nearest-neighbour (NN) thermodynamic model of
        SantaLucia & Hicks (1998) to compute the ΔG° of the n_terminal 3' bases
        of a primer. This value predicts polymerase extension efficiency: more
        negative ΔG → stronger 3' binding → higher amplification probability.

        The method uses the exact parameter values from Table 2 of:
            SantaLucia, J. (1998). A unified view of polymer, dumbbell, and
            oligonucleotide DNA nearest-neighbor thermodynamics.
            PNAS, 95(4), 1460–1465. doi:10.1073/pnas.95.4.1460

        Salt correction per Owczarzy et al. (2004). Biochemistry 43(12), 3537–3554.
            ΔG_corrected ≈ ΔG_1M + 0.114 × ln([Na+] / 1.0) × (N_pairs - 1)

        Args:
            sequence:      Full primer sequence (5' to 3'). Only the 3' terminal
                           n_terminal bases are evaluated.
            n_terminal:    Number of 3' terminal bases to include (default 5,
                           per Ye et al. 2012 NAR convention).
            temperature_c: Reaction temperature in °C (default 37°C, standard
                           for SantaLucia parameters).

        Returns:
            float: ΔG° in kcal/mol. Negative = thermodynamically stable 3' end.
                   Typical range: −5.5 (GC-rich) to −0.5 (AT-rich).
        """
        # ── SantaLucia 1998, Table 2 ────────────────────────────────────────
        # Unified nearest-neighbour parameters for DNA/DNA duplexes in 1M NaCl.
        # Key format: "XY" where X is 5'→3' base, Y is complement direction.
        # Canonical representation: 5'-XY-3' / 3'-X'Y'-5' dinucleotide stack.
        # ΔH° in kcal/mol, ΔS° in cal/(mol·K).
        # ΔG°(37°C) = ΔH° − (310.15 K) × ΔS° × 1e-3
        # All values are from Table 2, column "Unified" (SantaLucia 1998).
        # ─────────────────────────────────────────────────────────────────────
        _NN_DH: Dict[str, float] = {
            "AA": -7.9,  # AA/TT
            "AT": -7.2,  # AT/TA
            "TA": -7.2,  # TA/AT
            "CA": -8.5,  # CA/GT
            "GT": -8.4,  # GT/CA
            "CT": -7.8,  # CT/GA
            "GA": -8.2,  # GA/CT
            "CG": -10.6,  # CG/GC
            "GC": -9.8,  # GC/CG
            "GG": -8.0,  # GG/CC
        }
        _NN_DS: Dict[str, float] = {
            "AA": -22.2,  # AA/TT
            "AT": -20.4,  # AT/TA
            "TA": -21.3,  # TA/AT
            "CA": -22.7,  # CA/GT
            "GT": -22.4,  # GT/CA
            "CT": -21.0,  # CT/GA
            "GA": -22.2,  # GA/CT
            "CG": -27.2,  # CG/GC
            "GC": -24.4,  # GC/CG
            "GG": -19.9,  # GG/CC
        }
        # Complement map for canonical NN key lookup
        _COMP: Dict[str, str] = {"A": "T", "T": "A", "G": "C", "C": "G"}

        def _canonical_key(b1: str, b2: str) -> str:
            """Returns the canonical SantaLucia dinucleotide key.

            SantaLucia 1998 lists 10 unique NN pairs. For dinucleotides not
            directly in the table (e.g. TT, TC, TG), the complement strand
            read 5'→3' is equivalent: TT = complement of AA read reversed.
            """
            pair = b1 + b2
            if pair in _NN_DH:
                return pair
            # Try reverse complement: rev_comp of XY = comp(Y)+comp(X)
            rev_comp = _COMP.get(b2, "A") + _COMP.get(b1, "A")
            if rev_comp in _NN_DH:
                return rev_comp
            # Fallback to most common middle value (conservative)
            return "AT"

        # DNA sanitization
        seq_clean = "".join(c for c in sequence.upper() if c in "ATGC")
        if len(seq_clean) < 2:
            return 0.0
        seq = seq_clean

        # Take the 3' terminal n_terminal bases
        terminal = seq[-n_terminal:] if len(seq) >= n_terminal else seq

        T_kelvin = temperature_c + 273.15  # convert °C → K

        # Initiation parameters (SantaLucia 1998, Table 2 footnote):
        #   Terminal AT pair: ΔH=+2.3 kcal/mol, ΔS=+4.1 cal/mol·K
        #   Terminal GC pair: ΔH=+0.1 kcal/mol, ΔS=-2.8 cal/mol·K
        first_base = terminal[0]
        last_base = terminal[-1]
        if first_base in ("A", "T"):
            dh_init, ds_init = 2.3, 4.1
        else:
            dh_init, ds_init = 0.1, -2.8
        # Also add initiation for last base
        if last_base in ("A", "T"):
            dh_init += 2.3
            ds_init += 4.1
        else:
            dh_init += 0.1
            ds_init += -2.8

        # Sum NN contributions along the terminal sequence
        dh_total = dh_init
        ds_total = ds_init
        n_pairs = 0

        for i in range(len(terminal) - 1):
            b1 = terminal[i]
            b2 = terminal[i + 1]
            if b1 not in _COMP or b2 not in _COMP:
                continue  # skip degenerate bases
            key = _canonical_key(b1, b2)
            dh_total += _NN_DH[key]
            ds_total += _NN_DS[key]
            n_pairs += 1

        # ΔG°(T) = ΔH° − T × ΔS° (converting ΔS from cal to kcal)
        dg = dh_total - T_kelvin * (ds_total * 1e-3)

        # ── Owczarzy 2004 salt correction ────────────────────────────────────
        # Ref: Owczarzy et al. (2004). Biochemistry 43(12), 3537–3554.
        #      doi:10.1021/bi034621r
        # ΔG_corrected = ΔG_1M + 0.114 × ln([Na+]) × N_interior_pairs
        # where [Na+] is monovalent salt concentration in molar units.
        na_molar = self.salt_monovalent / 1000.0  # convert mM → M
        if na_molar > 0.0 and n_pairs > 0:
            import math

            salt_correction = 0.114 * math.log(na_molar) * n_pairs
            dg += salt_correction

        return round(dg, 4)

    def calculate_mismatch_penalty(
        self,
        primer_seq: str,
        template_seq: str,
        alpha: float = 0.15,
    ) -> float:
        """Computes position-specific mismatch thermodynamic extension penalties.

        Compares 5'→3' primer sequence against 3'→5' template binding sequence,
        identifies base-pairing mismatches, looks up their thermodynamic penalties,
        and applies an exponential 3'-extension penalty weight W(i) = e^(-alpha * dist).

        Args:
            primer_seq:   5' to 3' primer nucleotide sequence.
            template_seq: 3' to 5' template complementary binding sequence.
            alpha:        Exponential decay constant for 3' extension weight (default 0.15).

        Returns:
            float: Total position-weighted mismatch thermodynamic penalty in kcal/mol.
        """
        # Mismatch rules mapping (primer_base, template_base) to ΔΔG penalty
        _MISMATCH_RULES = {
            ("G", "T"): 1.0,
            ("T", "G"): 1.0,
            ("A", "G"): 2.5,
            ("G", "A"): 2.5,
            ("A", "A"): 3.0,
            ("T", "T"): 3.0,
            ("C", "T"): 3.0,
            ("T", "C"): 3.0,
            ("G", "G"): 3.0,
            ("C", "C"): 4.0,
            ("A", "C"): 4.0,
            ("C", "A"): 4.0,
        }

        _COMP = {"A": "T", "T": "A", "G": "C", "C": "G"}

        p_seq = primer_seq.upper().strip()
        t_seq = template_seq.upper().strip()

        # Alignment boundary check
        L = min(len(p_seq), len(t_seq))
        if L == 0:
            return 0.0

        import math

        total_penalty = 0.0

        for i in range(L):
            p_base = p_seq[i]
            t_base = t_seq[i]  # complementary target base (3'→5')

            if p_base not in _COMP or t_base not in _COMP:
                continue  # skip degenerate bases

            expected_match = _COMP[t_base]

            if p_base != expected_match:
                # We have a mismatch pairing!
                pair = (p_base, t_base)
                base_penalty = _MISMATCH_RULES.get(pair, 3.0)

                # Distance from the critical 3' end (index L-1)
                dist_from_3_prime = L - 1 - i
                weight = math.exp(-alpha * dist_from_3_prime)

                total_penalty += base_penalty * weight

        return round(total_penalty, 4)

    def generate_candidates(
        self, target_sequence: str, num_return: int = 100
    ) -> List[PrimerPair]:
        """Generates candidate primer pairs for a target template sequence using primer3 bindings.

        Args:
            target_sequence: Target DNA template sequence (5' to 3').
            num_return: Number of primer pairs to return.

        Returns:
            List[PrimerPair]: A list of designed primer pairs.
        """
        # Parse and sanitize DNA sequence: remove FASTA headers and strip all newlines/whitespaces
        lines = [line.strip() for line in target_sequence.split("\n") if line.strip()]
        if lines and lines[0].startswith(">"):
            lines = lines[1:]
        sequence_body = "".join(lines)
        seq_clean = "".join(c for c in sequence_body.upper() if c in "ATGC")

        logger.info(
            f"Generating candidate primer pairs for target sequence of length {len(seq_clean)}..."
        )

        seq_args = {
            "SEQUENCE_ID": "target_locus",
            "SEQUENCE_TEMPLATE": seq_clean,
        }

        global_args = {
            "PRIMER_OPT_SIZE": self.opt_size,
            "PRIMER_MIN_SIZE": self.min_size,
            "PRIMER_MAX_SIZE": self.max_size,
            "PRIMER_OPT_TM": self.opt_tm,
            "PRIMER_MIN_TM": self.min_tm,
            "PRIMER_MAX_TM": self.max_tm,
            "PRIMER_MIN_GC": 20.0,
            "PRIMER_MAX_GC": 80.0,
            "PRIMER_MAX_POLY_X": 5,
            "PRIMER_SALT_MONOVALENT": self.salt_monovalent,
            "PRIMER_SALT_DIVALENT": self.salt_divalent,
            "PRIMER_DNTP_CONC": self.dntp_conc,
            "PRIMER_NUM_RETURN": num_return,
            "PRIMER_PRODUCT_SIZE_RANGE": [[70, 150]],
        }

        try:
            results = primer3.bindings.design_primers(seq_args, global_args)
        except Exception as e:
            logger.error(f"Failed to generate primers using primer3 bindings: {e}")
            raise RuntimeError(f"Primer3 design failed: {e}")

        pairs_returned = results.get("PRIMER_PAIR_NUM_RETURNED", 0)
        logger.info(f"Primer3 successfully returned {pairs_returned} primer pairs.")

        primer_pairs = []
        for i in range(pairs_returned):
            # Parse forward primer
            f_seq = results[f"PRIMER_LEFT_{i}_SEQUENCE"]
            f_start, f_len = results[f"PRIMER_LEFT_{i}"]
            f_tm = results[f"PRIMER_LEFT_{i}_TM"]
            f_gc = results[f"PRIMER_LEFT_{i}_GC_PERCENT"]
            f_penalty = results[f"PRIMER_LEFT_{i}_PENALTY"]

            f_thermo = self.calculate_thermo_features(f_seq)
            forward_primer = PrimerSequence(
                sequence=f_seq,
                start=f_start,
                length=f_len,
                tm=f_tm,
                gc_percent=f_gc,
                hairpin_dg=f_thermo["hairpin_dg"],
                homodimer_dg=f_thermo["homodimer_dg"],
                penalty=f_penalty,
            )

            # Parse reverse primer
            r_seq = results[f"PRIMER_RIGHT_{i}_SEQUENCE"]
            r_start, r_len = results[f"PRIMER_RIGHT_{i}"]
            r_tm = results[f"PRIMER_RIGHT_{i}_TM"]
            r_gc = results[f"PRIMER_RIGHT_{i}_GC_PERCENT"]
            r_penalty = results[f"PRIMER_RIGHT_{i}_PENALTY"]

            r_thermo = self.calculate_thermo_features(r_seq)
            reverse_primer = PrimerSequence(
                sequence=r_seq,
                start=r_start,
                length=r_len,
                tm=r_tm,
                gc_percent=r_gc,
                hairpin_dg=r_thermo["hairpin_dg"],
                homodimer_dg=r_thermo["homodimer_dg"],
                penalty=r_penalty,
            )

            # Joint properties
            product_size = results[f"PRIMER_PAIR_{i}_PRODUCT_SIZE"]
            pair_penalty = results[f"PRIMER_PAIR_{i}_PENALTY"]
            cross_dimer_dg = self.calculate_heterodimer_dg(f_seq, r_seq)

            pair = PrimerPair(
                forward=forward_primer,
                reverse=reverse_primer,
                product_size=product_size,
                cross_dimer_dg=cross_dimer_dg,
                penalty=pair_penalty,
            )
            primer_pairs.append(pair)

        return primer_pairs
