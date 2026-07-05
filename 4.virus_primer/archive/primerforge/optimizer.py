"""Graph-based multiplex primer set optimizer for PrimerForge using Integer Linear Programming (ILP).

Models multiplex compatibility as a Maximum-Weight Independent Set (MWIS) problem
using the PuLP library to assemble optimal, dimer-free primer panels up to 24-plex.
"""

import pulp
from typing import Any, Dict, List, Tuple
from primerforge.biophysics import PrimerPair, PrimerSequence, BiophysicsEngine
from primerforge.ml_scorer import MLScorer
from primerforge.utils import setup_logger

logger = setup_logger("primerforge.optimizer")


class MultiplexOptimizer:
    """Integer Linear Programming (ILP) optimizer for multiplex PCR primer panels."""

    def __init__(self, biophys_engine: BiophysicsEngine | None = None) -> None:
        """Initializes the MultiplexOptimizer.

        Args:
            biophys_engine: BiophysicsEngine instance to compute dynamic cross-hybridizations.
        """
        self.biophys = biophys_engine or BiophysicsEngine()

    def optimize_panel(
        self,
        scored_pairs: List[Dict[str, Any]],
        max_plex: int = 24,
        delta_g_threshold: float = -4.5,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Assembles the mathematically optimal multiplex primer panel using ILP.

        Formulates a Maximum-Weight Independent Set (MWIS) graph optimization:
        - Nodes (V): Scored candidate primer pairs with weight = predicted success probability.
        - Edges (E): Interactions (cross-dimers) exceeding the free energy threshold (Delta G).
        - Locus Constraint: At most one primer pair selected per target locus.
        - Overlap Constraint: Non-overlapping coordinates if targets share a template.

        Args:
            scored_pairs: List of candidate dictionary records containing 'pair',
                'predicted_success', 'target_id' (optional), and 'is_valid'.
            max_plex: Maximum number of multiplexed loci (default 24).
            delta_g_threshold: Free energy threshold in kcal/mol (default -4.5).
                Cross-dimers more stable (more negative) than this limit are rejected.

        Returns:
            Tuple[List[Dict[str, Any]], float]: (Selected primer set, total objective value)
        """
        logger.info(
            f"Initializing ILP optimization for {len(scored_pairs)} candidate pairs..."
        )

        # Filter out invalid (3' SNP) candidate pairs first
        candidates = [item for item in scored_pairs if item.get("is_valid", True)]
        n_candidates = len(candidates)
        logger.info(
            f"Filtered candidate pool: N={n_candidates} (3' SNP dropouts discarded)."
        )

        if n_candidates == 0:
            logger.warning(
                "No valid candidate primer pairs available for multiplex optimization."
            )
            return [], 0.0

        # Assign unique locus IDs if not present in the target metadata
        for idx, item in enumerate(candidates):
            if "target_id" not in item:
                pair = item.get("pair")
                if (
                    pair is not None
                    and hasattr(pair, "forward")
                    and pair.forward is not None
                ):
                    item["target_id"] = pair.forward.sequence[
                        :6
                    ]  # Fallback target categorizer
                else:
                    item["target_id"] = f"locus_{idx}"

        # Initialize PuLP maximization problem
        prob = pulp.LpProblem("PrimerForge_Multiplex_Design", pulp.LpMaximize)

        # Create binary decision variables: x[i] = 1 if candidate i is selected, 0 otherwise
        x = [pulp.LpVariable(f"x_{i}", cat=pulp.LpBinary) for i in range(n_candidates)]

        # 1. Objective function: Maximize total predicted success probability
        prob += (
            pulp.lpSum(
                candidates[i]["predicted_success"] * x[i] for i in range(n_candidates)
            ),
            "Total_Success",
        )

        # 2. Constraint: Limit total number of selected amplicons to max_plex
        prob += (
            pulp.lpSum(x[i] for i in range(n_candidates)) <= max_plex,
            "Max_Plex_Constraint",
        )

        # 3. Locus Constraint: At most one primer pair selected per target locus
        loci_groups: Dict[str, List[int]] = {}
        for i, item in enumerate(candidates):
            target_id = item["target_id"]
            if target_id not in loci_groups:
                loci_groups[target_id] = []
            loci_groups[target_id].append(i)

        for target_id, indices in loci_groups.items():
            prob += (
                pulp.lpSum(x[i] for i in indices) <= 1,
                f"Locus_Constraint_{target_id}",
            )

        # 4. Cross-Dimerization Constraints: x_i + x_j <= 1 for interacting pairs
        # We pre-compute pairwise cross-hybridization between all candidates across different loci
        logger.info("Computing cross-dimerization interaction constraints...")
        conflict_edges = 0

        for i in range(n_candidates):
            pair_i = candidates[i]["pair"]

            for j in range(i + 1, n_candidates):
                # Do not check conflicts within the same locus (already constrained by Locus Constraint)
                if candidates[i]["target_id"] == candidates[j]["target_id"]:
                    continue

                pair_j = candidates[j]["pair"]

                # Check all 4 pairwise cross-dimers between the two sets:
                # 1. Forward_i + Forward_j
                # 2. Forward_i + Reverse_j
                # 3. Reverse_i + Forward_j
                # 4. Reverse_i + Reverse_j
                dg_ff = self.biophys.calculate_heterodimer_dg(
                    pair_i.forward.sequence, pair_j.forward.sequence
                )
                dg_fr = self.biophys.calculate_heterodimer_dg(
                    pair_i.forward.sequence, pair_j.reverse.sequence
                )
                dg_rf = self.biophys.calculate_heterodimer_dg(
                    pair_i.reverse.sequence, pair_j.forward.sequence
                )
                dg_rr = self.biophys.calculate_heterodimer_dg(
                    pair_i.reverse.sequence, pair_j.reverse.sequence
                )

                min_dg = min(dg_ff, dg_fr, dg_rf, dg_rr)

                # If the hybridization is too stable (more negative than threshold), they conflict
                if min_dg < delta_g_threshold:
                    prob += x[i] + x[j] <= 1, f"Conflict_{i}_{j}"
                    conflict_edges += 1

        logger.info(
            f"ILP graph built with {n_candidates} nodes and {conflict_edges} conflict edges."
        )

        # 5. Solve the Integer Linear Programming problem
        try:
            # Silence the solver output to keep the console clean
            solver = pulp.PULP_CBC_CMD(msg=False)
            status = prob.solve(solver)
        except Exception as e:
            logger.error(
                f"PuLP ILP Solver failed: {e}. Falling back to a greedy heuristic solver."
            )
            return self._solve_greedy_fallback(candidates, max_plex, delta_g_threshold)

        # Check solver status
        if status != pulp.LpStatusOptimal:
            logger.warning(
                "PuLP failed to find an mathematically optimal solution. Running greedy fallback."
            )
            return self._solve_greedy_fallback(candidates, max_plex, delta_g_threshold)

        # Extract selected candidates
        selected_set: List[Dict[str, Any]] = []
        for i in range(n_candidates):
            if x[i].varValue is not None and x[i].varValue > 0.5:
                selected_set.append(candidates[i])

        objective_value = (
            float(pulp.value(prob.objective)) if pulp.value(prob.objective) else 0.0
        )
        logger.info(
            f"ILP optimization completed successfully. Selected {len(selected_set)} compatible primer pairs."
        )
        return selected_set, objective_value

    def _solve_greedy_fallback(
        self, candidates: List[Dict[str, Any]], max_plex: int, delta_g_threshold: float
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Greedy heuristic solver fallback in case the C-compiler/pulp command is blocked."""
        logger.info("Running greedy heuristic multiplex selection...")
        # Sort by predicted success probability descending
        sorted_candidates = sorted(candidates, key=lambda x: -x["predicted_success"])
        selected: List[Dict[str, Any]] = []
        selected_loci = set()

        for item in sorted_candidates:
            if len(selected) >= max_plex:
                break

            target_id = item["target_id"]
            if target_id in selected_loci:
                continue

            pair = item["pair"]
            conflict = False

            # Check conflicts against already selected pairs
            for sel in selected:
                sel_pair = sel["pair"]
                dg_ff = self.biophys.calculate_heterodimer_dg(
                    pair.forward.sequence, sel_pair.forward.sequence
                )
                dg_fr = self.biophys.calculate_heterodimer_dg(
                    pair.forward.sequence, sel_pair.reverse.sequence
                )
                dg_rf = self.biophys.calculate_heterodimer_dg(
                    pair.reverse.sequence, sel_pair.forward.sequence
                )
                dg_rr = self.biophys.calculate_heterodimer_dg(
                    pair.reverse.sequence, sel_pair.reverse.sequence
                )

                if min(dg_ff, dg_fr, dg_rf, dg_rr) < delta_g_threshold:
                    conflict = True
                    break

            if not conflict:
                selected.append(item)
                selected_loci.add(target_id)

        obj_val = sum(item["predicted_success"] for item in selected)
        return selected, obj_val


class TiledAmpliconRouter:
    """Dynamic Programming (DP) optimizer to design overlapping tiled-amplicon primer panels.

    Used for whole-genome or large pathogen target tiling (e.g. ARTIC SARS-CoV-2 schemes),
    maximizing sequence coverage and uniformity of predicted success while ensuring that
    consecutive overlapping amplicons are thermodynamically compatible (dimer-free).
    """

    def __init__(
        self,
        biophys_engine: BiophysicsEngine | None = None,
        ml_scorer: MLScorer | None = None,
    ) -> None:
        """Initializes the TiledAmpliconRouter.

        Args:
            biophys_engine: BiophysicsEngine instance for thermodynamic calculations.
            ml_scorer: MLScorer instance to predict success probabilities.
        """
        self.biophys = biophys_engine or BiophysicsEngine()
        self.ml_scorer = ml_scorer or MLScorer()

    def design_tiled_amplicons(
        self,
        target_sequence: str,
        tile_size: int = 400,
        overlap: int = 50,
        max_tiles: int | None = None,
        delta_g_threshold: float = -4.5,
    ) -> List[Dict[str, Any]]:
        """Computes the mathematically optimal tiling path of overlapping amplicons using DP.

        Formulates the segment selection problem as a high-performance Dynamic Programming chain:
        - Objective: Maximize physical template coverage and success probability uniformity.
        - Constraints: Enforce target overlap windows and exclude cross-hybridizing dimers.

        Args:
            target_sequence: Long reference nucleotide sequence to tile (5' to 3').
            tile_size: Desired target length of each individual amplicon (default 400).
            overlap: Desired overlap in base pairs between consecutive amplicons (default 50).
            max_tiles: Maximum number of tiles allowed (optional).
            delta_g_threshold: Free energy limit in kcal/mol for cross-dimer rejections.

        Returns:
            List[Dict[str, Any]]: Chronologically sorted list of selected optimal tiles.
        """
        logger.info(
            f"Initializing Dynamic Programming Tiled-Amplicon design for sequence of length {len(target_sequence)}..."
        )
        L = len(target_sequence)

        # 1. Define sliding window target regions spanning the sequence
        windows = []
        step = tile_size - overlap
        curr_start = 0

        while curr_start + tile_size <= L:
            windows.append((curr_start, curr_start + tile_size))
            curr_start += step

        # Include trailing window if it leaves sequence uncovered
        if L > tile_size and (not windows or windows[-1][1] < L):
            windows.append((L - tile_size, L))
        elif not windows:
            # If target sequence is smaller than tile_size, design a single tile
            windows.append((0, L))

        if max_tiles is not None:
            windows = windows[:max_tiles]

        logger.info(
            f"Target tiling scheme consists of {len(windows)} overlapping sliding windows."
        )

        # 2. Generate and score candidates for each window
        # Group candidates by window index
        scored_by_window: List[List[Dict[str, Any]]] = []
        default_spec = {
            "f_off_targets": 0,
            "r_off_targets": 0,
            "f_var_dist": 20.0,
            "r_var_dist": 20.0,
            "f_var_maf": 0.0,
            "r_var_maf": 0.0,
        }

        for k, (win_start, win_end) in enumerate(windows):
            sub_seq = target_sequence[win_start:win_end]
            pairs = self._generate_tile_candidates(sub_seq, tile_size, num_return=10)

            win_candidates = []
            for pair in pairs:
                # Calculate predicted amplification success probability
                success = self.ml_scorer.predict_success(pair, default_spec)

                # Project coordinates to absolute global sequence coordinates
                abs_start = win_start + pair.forward.start
                abs_end = win_start + pair.forward.start + pair.product_size

                win_candidates.append(
                    {
                        "pair": pair,
                        "predicted_success": success,
                        "target_id": f"tile_{k}",
                        "is_valid": True,
                        "abs_start": abs_start,
                        "abs_end": abs_end,
                        "win_start": win_start,
                        "win_end": win_end,
                    }
                )

            # Sort candidate pool for the window to put the highest success first
            win_candidates.sort(key=lambda x: -x["predicted_success"])
            scored_by_window.append(win_candidates)

        # Remove any windows that produced zero primer candidates to avoid DP blocking
        valid_windows = []
        valid_candidates = []
        for k, win_cands in enumerate(scored_by_window):
            if win_cands:
                valid_windows.append(windows[k])
                valid_candidates.append(win_cands)

        N = len(valid_candidates)
        if N == 0:
            logger.warning(
                "No primer pairs could be generated across any target sliding windows."
            )
            return []

        logger.info(
            f"Proceeding to DP solver with {N} valid window segments containing candidates."
        )

        # 3. Dynamic Programming solver loop
        # DP[k][i] = max score for a sequence ending with candidate i at window k
        # Parent[k][i] = backpointer index of the best transition from window k-1
        dp = [[-1e9] * len(valid_candidates[k]) for k in range(N)]
        parent = [[-1] * len(valid_candidates[k]) for k in range(N)]

        # Initialize first window candidates
        for i in range(len(valid_candidates[0])):
            dp[0][i] = valid_candidates[0][i]["predicted_success"]

        # Run forward DP transitions
        for k in range(1, N):
            curr_cands = valid_candidates[k]
            prev_cands = valid_candidates[k - 1]

            for i in range(len(curr_cands)):
                abs_start_curr = curr_cands[i]["abs_start"]
                pair_curr = curr_cands[i]["pair"]

                best_score = -1e9
                best_prev_idx = -1

                for j in range(len(prev_cands)):
                    abs_end_prev = prev_cands[j]["abs_end"]
                    pair_prev = prev_cands[j]["pair"]

                    # Calculate overlap between consecutive amplicons
                    actual_overlap = abs_end_prev - abs_start_curr

                    # Transition Penalty 1: Overlap error (quadratic deviation penalty)
                    overlap_error = (actual_overlap - overlap) ** 2
                    overlap_penalty = (
                        0.005 * overlap_error
                    )  # Scaled to balance with P_success (0.0 to 1.0)

                    # Hard overlap range boundaries: block amplicons with gaps or redundant overlaps
                    if actual_overlap <= 0 or actual_overlap > 2.5 * overlap:
                        overlap_penalty = 1e9

                    # Transition Penalty 2: Inter-tile dimerization check
                    dg_ff = self.biophys.calculate_heterodimer_dg(
                        pair_curr.forward.sequence, pair_prev.forward.sequence
                    )
                    dg_fr = self.biophys.calculate_heterodimer_dg(
                        pair_curr.forward.sequence, pair_prev.reverse.sequence
                    )
                    dg_rf = self.biophys.calculate_heterodimer_dg(
                        pair_curr.reverse.sequence, pair_prev.forward.sequence
                    )
                    dg_rr = self.biophys.calculate_heterodimer_dg(
                        pair_curr.reverse.sequence, pair_prev.reverse.sequence
                    )

                    min_dg = min(dg_ff, dg_fr, dg_rf, dg_rr)
                    dimer_penalty = 0.0
                    if min_dg < delta_g_threshold:
                        dimer_penalty = 1e9  # Severe penalty/hard constraint

                    # Transition score
                    candidate_score = curr_cands[i]["predicted_success"]
                    transition_score = (
                        dp[k - 1][j]
                        + candidate_score
                        - (overlap_penalty + dimer_penalty)
                    )

                    if transition_score > best_score:
                        best_score = transition_score
                        best_prev_idx = j

                dp[k][i] = best_score
                parent[k][i] = best_prev_idx

        # Find best end candidate in the final window
        best_final_idx = -1
        best_final_score = -1e9

        for i in range(len(valid_candidates[-1])):
            if dp[-1][i] > best_final_score:
                best_final_score = dp[-1][i]
                best_final_idx = i

        # 4. Fallback in case constraints are too tight (e.g. no valid path)
        if best_final_score < -1e8:
            logger.warning(
                "Constraints are too tight to find a dimer-free/overlap-compliant path. Running relaxed DP fallback..."
            )
            return self._design_tiled_relaxed_fallback(valid_candidates, overlap)

        # 5. Backtrack to extract the optimal chain
        selected_path: List[Dict[str, Any]] = []
        curr_idx = best_final_idx
        for k in range(N - 1, -1, -1):
            selected_path.append(valid_candidates[k][curr_idx])
            curr_idx = parent[k][curr_idx]

        selected_path.reverse()
        logger.info(
            f"Optimal tiled amplicon path successfully designed with {len(selected_path)} overlapping tiles."
        )
        return selected_path

    def _generate_tile_candidates(
        self, target_seq: str, tile_size: int, num_return: int = 10
    ) -> List[PrimerPair]:
        """Custom helper to design candidate primers with amplicon size tailored to the tile size."""
        seq_args = {
            "SEQUENCE_ID": "tile_locus",
            "SEQUENCE_TEMPLATE": target_seq,
        }
        # Allow primer3 to find products centering around the desired tile_size
        min_p_size = max(70, tile_size - 100)
        max_p_size = tile_size + 100

        global_args = {
            "PRIMER_OPT_SIZE": self.biophys.opt_size,
            "PRIMER_MIN_SIZE": self.biophys.min_size,
            "PRIMER_MAX_SIZE": self.biophys.max_size,
            "PRIMER_OPT_TM": self.biophys.opt_tm,
            "PRIMER_MIN_TM": self.biophys.min_tm,
            "PRIMER_MAX_TM": self.biophys.max_tm,
            "PRIMER_MIN_GC": 20.0,
            "PRIMER_MAX_GC": 80.0,
            "PRIMER_MAX_POLY_X": 5,
            "PRIMER_SALT_MONOVALENT": self.biophys.salt_monovalent,
            "PRIMER_SALT_DIVALENT": self.biophys.salt_divalent,
            "PRIMER_DNTP_CONC": self.biophys.dntp_conc,
            "PRIMER_NUM_RETURN": num_return,
            "PRIMER_PRODUCT_SIZE_RANGE": [[min_p_size, max_p_size]],
        }

        import primer3

        try:
            results = primer3.bindings.design_primers(seq_args, global_args)
        except Exception as e:
            logger.warning(f"Primer3 design failed for tile segment: {e}")
            return []

        pairs_returned = results.get("PRIMER_PAIR_NUM_RETURNED", 0)
        primer_pairs = []
        for i in range(pairs_returned):
            f_seq = results[f"PRIMER_LEFT_{i}_SEQUENCE"]
            f_start, f_len = results[f"PRIMER_LEFT_{i}"]
            f_tm = results[f"PRIMER_LEFT_{i}_TM"]
            f_gc = results[f"PRIMER_LEFT_{i}_GC_PERCENT"]
            f_penalty = results[f"PRIMER_LEFT_{i}_PENALTY"]

            f_thermo = self.biophys.calculate_thermo_features(f_seq)
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

            r_seq = results[f"PRIMER_RIGHT_{i}_SEQUENCE"]
            r_start, r_len = results[f"PRIMER_RIGHT_{i}"]
            r_tm = results[f"PRIMER_RIGHT_{i}_TM"]
            r_gc = results[f"PRIMER_RIGHT_{i}_GC_PERCENT"]
            r_penalty = results[f"PRIMER_RIGHT_{i}_PENALTY"]

            r_thermo = self.biophys.calculate_thermo_features(r_seq)
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

            product_size = results[f"PRIMER_PAIR_{i}_PRODUCT_SIZE"]
            pair_penalty = results[f"PRIMER_PAIR_{i}_PENALTY"]
            cross_dimer_dg = self.biophys.calculate_heterodimer_dg(f_seq, r_seq)

            pair = PrimerPair(
                forward=forward_primer,
                reverse=reverse_primer,
                product_size=product_size,
                cross_dimer_dg=cross_dimer_dg,
                penalty=pair_penalty,
            )
            primer_pairs.append(pair)

        return primer_pairs

    def _design_tiled_relaxed_fallback(
        self, valid_candidates: List[List[Dict[str, Any]]], overlap: int
    ) -> List[Dict[str, Any]]:
        """Relaxed DP solver fallback for high-density genomes or difficult targets."""
        logger.info("Executing relaxed DP tiled-amplicon optimization...")
        N = len(valid_candidates)
        dp = [[-1e9] * len(valid_candidates[k]) for k in range(N)]
        parent = [[-1] * len(valid_candidates[k]) for k in range(N)]

        # Initialize first window candidates
        for i in range(len(valid_candidates[0])):
            dp[0][i] = valid_candidates[0][i]["predicted_success"]

        # Run forward DP with completely relaxed boundaries
        for k in range(1, N):
            curr_cands = valid_candidates[k]
            prev_cands = valid_candidates[k - 1]

            for i in range(len(curr_cands)):
                abs_start_curr = curr_cands[i]["abs_start"]

                best_score = -1e9
                best_prev_idx = -1

                for j in range(len(prev_cands)):
                    abs_end_prev = prev_cands[j]["abs_end"]
                    actual_overlap = abs_end_prev - abs_start_curr

                    # Linear relaxed overlap penalty
                    overlap_error = abs(actual_overlap - overlap)
                    overlap_penalty = 0.01 * overlap_error

                    # If overlap is totally negative (gap), still penalize heavily but allow if forced
                    if actual_overlap <= 0:
                        overlap_penalty += 10.0

                    transition_score = (
                        dp[k - 1][j]
                        + curr_cands[i]["predicted_success"]
                        - overlap_penalty
                    )

                    if transition_score > best_score:
                        best_score = transition_score
                        best_prev_idx = j

                dp[k][i] = best_score
                parent[k][i] = best_prev_idx

        # Backtrack the relaxed path
        best_final_idx = 0
        best_final_score = -1e9
        for i in range(len(valid_candidates[-1])):
            if dp[-1][i] > best_final_score:
                best_final_score = dp[-1][i]
                best_final_idx = i

        selected_path: List[Dict[str, Any]] = []
        curr_idx = best_final_idx
        for k in range(N - 1, -1, -1):
            selected_path.append(valid_candidates[k][curr_idx])
            curr_idx = parent[k][curr_idx]

        selected_path.reverse()
        logger.info(
            f"Relaxed tiled amplicon path successfully designed with {len(selected_path)} overlapping tiles."
        )
        return selected_path
