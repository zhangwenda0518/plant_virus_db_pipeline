"""Multiplex Cross-Reactivity Optimization module for PrimerForge.

Provides combinatorial dimerization matrix construction, global multiplex panel
penalty scoring, and a greedy selection algorithm to filter compatible primer pools.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Any, Optional
import numpy as np

from primerforge.biophysics import PrimerPair, BiophysicsEngine
from primerforge.utils import setup_logger

logger = setup_logger("primerforge.multiplex")


@dataclass
class MultiplexPanel:
    """Represents a designed panel of compatible primer pairs for multiplex PCR.

    Attributes:
        pairs:              List of selected compatible PrimerPair objects.
        dimerization_matrix: Matrix of shape (2M, 2M) holding dimerization free energies.
        global_penalty:     Sum of all base-pairing penalties exceeding threshold.
        primer_labels:      List of names/labels mapping rows/cols in the matrix to sequences.
    """

    pairs: List[PrimerPair]
    dimerization_matrix: np.ndarray
    global_penalty: float
    primer_labels: List[str]


class MultiplexOptimizer:
    """Optimizes multiplex primer panel design by minimizing cross-reactivity and dimerization."""

    def __init__(self, biophysics_engine: Optional[BiophysicsEngine] = None) -> None:
        """Initializes the MultiplexOptimizer with a BiophysicsEngine instance."""
        self.engine = (
            biophysics_engine if biophysics_engine is not None else BiophysicsEngine()
        )

    def build_dimerization_matrix(
        self, pairs: List[PrimerPair]
    ) -> Tuple[np.ndarray, List[str]]:
        """Constructs a symmetric (2M, 2M) dimerization free energy matrix.

        Off-diagonal entries represent heterodimerization stability between different primers.
        Diagonal entries represent homodimerization stability of each primer.

        Args:
            pairs: List of selected PrimerPair objects.

        Returns:
            Tuple[np.ndarray, List[str]]: (dimerization_matrix, primer_labels)
        """
        M = len(pairs)
        N = 2 * M
        matrix = np.zeros((N, N), dtype=np.float32)

        # Extract sequences and labels
        sequences = []
        labels = []
        for idx, pair in enumerate(pairs):
            # Forward primer
            sequences.append(pair.forward.sequence)
            labels.append(f"Pair_{idx}_F")
            # Reverse primer
            sequences.append(pair.reverse.sequence)
            labels.append(f"Pair_{idx}_R")

        # Fill the symmetric matrix
        for j in range(N):
            for k in range(j, N):
                seq_j = sequences[j]
                seq_k = sequences[k]

                if j == k:
                    # Homodimer stability
                    features = self.engine.calculate_thermo_features(seq_j)
                    dg = float(features.get("homodimer_dg", 0.0))
                else:
                    # Heterodimer stability
                    dg = float(self.engine.calculate_heterodimer_dg(seq_j, seq_k))

                matrix[j, k] = dg
                matrix[k, j] = dg  # Symmetric entry

        return matrix, labels

    def calculate_multiplex_penalty(
        self, matrix: np.ndarray, threshold: float = -6.0
    ) -> float:
        """Calculates global multiplex cross-reactivity penalty based on the dimerization matrix.

        Accumulates penalties only for dimerization stabilities between different primer pairs
        that exceed the threshold (more negative than threshold). Internal homodimers and
        heterodimers within the same pair are excluded.

        Args:
            matrix:    Symmetric dimerization matrix of shape (2M, 2M).
            threshold: Dimerization threshold in kcal/mol (default: -6.0).

        Returns:
            float: Accumulate cross-reactivity penalty score.
        """
        N = matrix.shape[0]
        total_penalty = 0.0

        # Loop over upper triangle to prevent double counting
        for j in range(N):
            for k in range(j, N):
                # Check if primers belong to different pairs
                if j // 2 != k // 2:
                    dg = matrix[j, k]
                    # More negative than threshold means stronger, unwanted dimerization
                    if dg < threshold:
                        # Penalty is the excess stability (positive value)
                        total_penalty += float(abs(dg - threshold))

        return round(total_penalty, 4)

    def design_compatible_panel(
        self,
        candidate_pools: List[List[PrimerPair]],
        threshold: float = -6.0,
        hard_limit: float = -9.0,
    ) -> MultiplexPanel:
        """Greedily designs a highly compatible multiplex panel from locus candidate pools.

        Evaluates cross-reactivity dimerization, rejects highly cross-reactive candidates,
        and selects compatible alternative pairs to rescue the panel from failures.

        Args:
            candidate_pools: List of candidate PrimerPair pools, one list per target locus.
            threshold:       Dimerization threshold for soft penalty calculation (default: -6.0).
            hard_limit:      Severe dimerization threshold above which a candidate is rejected (default: -9.0).

        Returns:
            MultiplexPanel: Optimized panel of compatible pairs.
        """
        if not candidate_pools:
            logger.warning("Empty candidate pools provided to design_compatible_panel")
            return MultiplexPanel([], np.zeros((0, 0)), 0.0, [])

        selected_pairs: List[PrimerPair] = []

        # 1. Initialize with the highest-ranked primer pair for the first target locus
        first_pool = candidate_pools[0]
        if not first_pool:
            raise ValueError("Candidate pool for target locus index 0 is empty.")
        selected_pairs.append(first_pool[0])

        # 2. Iteratively process candidate pools for subsequent loci
        for locus_idx in range(1, len(candidate_pools)):
            pool = candidate_pools[locus_idx]
            if not pool:
                raise ValueError(
                    f"Candidate pool for target locus index {locus_idx} is empty."
                )

            best_candidate: Optional[PrimerPair] = None
            min_incremental_penalty = float("inf")
            best_matrix: Optional[np.ndarray] = None
            best_labels: Optional[List[str]] = None

            # Evaluate each candidate pair in the pool for compatibility with already selected pairs
            for candidate in pool:
                test_set = selected_pairs + [candidate]
                matrix, labels = self.build_dimerization_matrix(test_set)

                # Check for absolute severe cross-reactivity limit
                # We scan only the new primer interactions against existing primers (the last two rows/cols)
                N_test = matrix.shape[0]
                severe_crossover = False
                for j in range(N_test - 2, N_test):
                    for k in range(N_test):
                        if j != k and matrix[j, k] < hard_limit:
                            severe_crossover = True
                            break
                    if severe_crossover:
                        break

                if severe_crossover:
                    logger.debug(
                        f"Candidate from locus {locus_idx} rejected due to severe dimerization (exceeded {hard_limit} kcal/mol)."
                    )
                    continue  # Reject candidate immediately

                penalty = self.calculate_multiplex_penalty(matrix, threshold)

                # We want to minimize the global penalty, or break ties using individual penalty/rank
                if penalty < min_incremental_penalty:
                    min_incremental_penalty = penalty
                    best_candidate = candidate
                    best_matrix = matrix
                    best_labels = labels

            # Rescue fallback: If all candidates in the pool violated the hard limit,
            # fall back to the first candidate of the pool to ensure panel continuity, but print warning.
            if best_candidate is None:
                logger.warning(
                    f"All candidates for locus index {locus_idx} violated hard dimerization limit. Forcing fallback to top-ranked candidate."
                )
                best_candidate = pool[0]
                test_set = selected_pairs + [best_candidate]
                best_matrix, best_labels = self.build_dimerization_matrix(test_set)
                min_incremental_penalty = self.calculate_multiplex_penalty(
                    best_matrix, threshold
                )

            selected_pairs.append(best_candidate)

        # 3. Final dimerization matrix and penalty scoring for the complete optimized panel
        final_matrix, final_labels = self.build_dimerization_matrix(selected_pairs)
        final_penalty = self.calculate_multiplex_penalty(final_matrix, threshold)

        logger.info(
            f"Multiplex panel designed successfully! Selected {len(selected_pairs)} compatible pairs with a global penalty of {final_penalty:.4f}."
        )
        return MultiplexPanel(selected_pairs, final_matrix, final_penalty, final_labels)
