"""Active Learning & Bayesian Uncertainty Engine for PrimerForge.

Supports uncertainty estimation using the stacked booster ensemble and training
with acquisition strategies (Entropy, Epistemic, Aleatoric, Hybrid, Random).
"""

import os
import random
import numpy as np
import pandas as pd
try:
    import lightgbm as lgb
except ImportError:
    lgb = None
from typing import Any, Dict, List, Tuple

from primerforge.biophysics import PrimerPair
from primerforge.ml_scorer import MLScorer, NumPyMLPRegressor
from primerforge.utils import setup_logger

logger = setup_logger("primerforge.active_learning")


class BiophysicalOracle:
    """Simulates a wet-lab PCR amplification assay.

    Uses sequence, thermodynamic, and variant features to compute a true physical
    amplification probability and draws binary outcomes with experimental noise.
    """

    def __init__(self, noise_std: float = 0.1, threshold_dg: float = -3.0) -> None:
        self.noise_std = noise_std
        self.threshold_dg = threshold_dg

    def evaluate(
        self,
        pair: PrimerPair,
        spec_data: Dict[str, Any] | None = None,
        deterministic: bool = False,
    ) -> int:
        """Computes true amplification probability and returns binary success (0 or 1)."""
        spec = spec_data or {}
        f_seq = pair.forward.sequence.upper()
        r_seq = pair.reverse.sequence.upper()

        penalty = 0.0

        # 1. Tm Difference
        tm_diff = abs(pair.forward.tm - pair.reverse.tm)
        if tm_diff > 2.0:
            penalty += (tm_diff - 2.0) * 1.5

        # 2. Dimer delta G
        homodimer_dg = min(pair.forward.homodimer_dg, pair.reverse.homodimer_dg)
        if homodimer_dg < -4.0:
            penalty += abs(homodimer_dg + 4.0) * 1.0

        hairpin_dg = min(pair.forward.hairpin_dg, pair.reverse.hairpin_dg)
        if hairpin_dg < -3.0:
            penalty += abs(hairpin_dg + 3.0) * 1.2

        cross_dimer_dg = pair.cross_dimer_dg
        if cross_dimer_dg < -5.0:
            penalty += abs(cross_dimer_dg + 5.0) * 1.5

        # 3. Off-targets
        f_off = float(spec.get("f_off_targets", 0))
        r_off = float(spec.get("r_off_targets", 0))
        if f_off > 0 or r_off > 0:
            penalty += (f_off + r_off) * 2.0

        # 4. SNP / Variant dropouts near 3' end
        f_var_dist = float(spec.get("f_var_dist", 20.0))
        r_var_dist = float(spec.get("r_var_dist", 20.0))
        f_maf = float(spec.get("f_var_maf", 0.0))
        r_maf = float(spec.get("r_var_maf", 0.0))

        if f_var_dist < 5.0 and f_maf > 0.01:
            penalty += (5.0 - f_var_dist) * 2.5 * f_maf
        if r_var_dist < 5.0 and r_maf > 0.01:
            penalty += (5.0 - r_var_dist) * 2.5 * r_maf

        # 5. GC Clamps & Homopolymer Run
        f_clamp = float(sum(1 for b in f_seq[-5:] if b in "GC"))
        r_clamp = float(sum(1 for b in r_seq[-5:] if b in "GC"))
        if f_clamp == 0 or f_clamp == 5:
            penalty += 1.0
        if r_clamp == 0 or r_clamp == 5:
            penalty += 1.0

        def get_max_run(seq: str) -> int:
            if not seq:
                return 0
            max_run = 1
            current = 1
            for i in range(1, len(seq)):
                if seq[i] == seq[i - 1]:
                    current += 1
                else:
                    max_run = max(max_run, current)
                    current = 1
            return max(max_run, current)

        max_run = max(get_max_run(f_seq), get_max_run(r_seq))
        if max_run > 4:
            penalty += (max_run - 4) * 1.5

        # Sigmoid probability of success: lower penalty -> higher success
        # When penalty = 0, p_success = sigmoid(3.0) = 0.952
        # When penalty = 3.0, p_success = sigmoid(0.0) = 0.500
        p_success = 1.0 / (1.0 + np.exp(penalty - 3.0))

        if deterministic:
            return 1 if p_success >= 0.5 else 0

        # Add Gaussian noise to decision threshold
        noise = np.random.normal(0, self.noise_std)
        outcome = (p_success + noise) > 0.5
        return 1 if outcome else 0


class ActiveLearningEngine:
    """Manages active learning loop using ensembled MLScorer and BiophysicalOracle."""

    def __init__(self, scorer: MLScorer, oracle: BiophysicalOracle) -> None:
        self.scorer = scorer
        self.oracle = oracle
        self.labeled_pool: List[Tuple[PrimerPair, Dict[str, Any], int]] = []
        self.unlabeled_pool: List[Tuple[PrimerPair, Dict[str, Any]]] = []

    def load_initial_labeled_data(
        self, data: List[Tuple[PrimerPair, Dict[str, Any], int]]
    ) -> None:
        """Loads the starting training set."""
        self.labeled_pool.extend(data)

    def load_unlabeled_pool(
        self, data: List[Tuple[PrimerPair, Dict[str, Any]]]
    ) -> None:
        """Loads candidates to choose from."""
        self.unlabeled_pool.extend(data)

    def compute_acquisition_scores(self, strategy: str) -> np.ndarray:
        """Computes scoring metrics for all candidates in the unlabeled pool."""
        N = len(self.unlabeled_pool)
        if N == 0:
            return np.array([], dtype=np.float32)

        if strategy == "random":
            return np.random.rand(N).astype(np.float32)

        probs = []
        epistemics = []
        aleatorics = []

        # Find quantile boosters in ensemble
        quantile_boosters = [
            b
            for b in self.scorer.models
            if getattr(b, "objective_type", b.params.get("objective")) == "quantile"
        ]

        for pair, spec_data in self.unlabeled_pool:
            p, std_pred = self.scorer.predict_success_with_uncertainty(pair, spec_data)
            probs.append(p)
            epistemics.append(std_pred)

            # Compute prediction interval width as proxy for aleatoric uncertainty
            if len(quantile_boosters) >= 2:
                features = np.array(
                    [self.scorer.extract_features(pair, spec_data)], dtype=np.float32
                )
                q05 = float(quantile_boosters[0].predict(features)[0])
                q95 = float(quantile_boosters[1].predict(features)[0])
                # Calibrate lower/upper boundaries
                lower = 1.0 / (
                    1.0 + np.exp(self.scorer.platt_a * q05 + self.scorer.platt_b)
                )
                upper = 1.0 / (
                    1.0 + np.exp(self.scorer.platt_a * q95 + self.scorer.platt_b)
                )
                width = abs(upper - lower)
            else:
                # Fallback prediction interval width
                width = 1.96 * std_pred
            aleatorics.append(width)

        probs = np.array(probs, dtype=np.float32)
        epistemics = np.array(epistemics, dtype=np.float32)
        aleatorics = np.array(aleatorics, dtype=np.float32)

        if strategy == "entropy":
            # Shannon Entropy H(p) = -p log2(p) - (1-p) log2(1-p)
            # Clip probability boundaries to prevent log(0)
            p_clamped = np.clip(probs, 1e-6, 1.0 - 1e-6)
            entropy = -p_clamped * np.log2(p_clamped) - (1.0 - p_clamped) * np.log2(
                1.0 - p_clamped
            )
            return entropy

        elif strategy == "epistemic":
            return epistemics

        elif strategy == "aleatoric":
            return aleatorics

        elif strategy == "hybrid":
            # Hybrid matches Normalized Entropy + Normalized Epistemic
            p_clamped = np.clip(probs, 1e-6, 1.0 - 1e-6)
            entropy = -p_clamped * np.log2(p_clamped) - (1.0 - p_clamped) * np.log2(
                1.0 - p_clamped
            )

            def norm(arr: np.ndarray) -> np.ndarray:
                mn, mx = arr.min(), arr.max()
                if mx - mn > 1e-8:
                    return (arr - mn) / (mx - mn)
                return np.zeros_like(arr)

            return 0.5 * norm(entropy) + 0.5 * norm(epistemics)

        else:
            raise ValueError(f"Unknown active learning strategy: {strategy}")

    def query_and_label_next_batch(
        self, batch_size: int, strategy: str, deterministic: bool = False
    ) -> List[Tuple[PrimerPair, Dict[str, Any], int]]:
        """Queries the top K candidates using the selected strategy, labels them, and moves them to training."""
        N = len(self.unlabeled_pool)
        if N == 0:
            return []

        actual_batch = min(batch_size, N)
        scores = self.compute_acquisition_scores(strategy)

        # Sort in descending order of score
        ranked_indices = np.argsort(scores)[::-1]
        selected_pool_indices = ranked_indices[:actual_batch]

        # Extract queried candidates
        queried = []
        for idx in sorted(selected_pool_indices, reverse=True):
            pair, spec_data = self.unlabeled_pool.pop(idx)
            label = self.oracle.evaluate(pair, spec_data, deterministic=deterministic)
            queried.append((pair, spec_data, label))

        # Add queries to labeled pool
        self.labeled_pool.extend(queried)
        logger.info(
            f"Queried and labeled {actual_batch} candidates using strategy '{strategy}'."
        )
        return queried

    def retrain_ensemble(self) -> None:
        """Retrains all boosters in the ensemble using the updated labeled training dataset."""
        N = len(self.labeled_pool)
        if N < 10:
            logger.warning(
                f"Labeled training set size too small ({N}). Skipping retraining."
            )
            return

        logger.info(f"Retraining stacked ensemble on N={N} labeled samples...")

        # 1. Build features and labels
        X_list = []
        y_list = []
        for pair, spec_data, label in self.labeled_pool:
            X_list.append(self.scorer.extract_features(pair, spec_data))
            y_list.append(float(label))

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.float32)

        # 2. Fit standard regression boosters (3 bootstrap ensemble seeds)
        seeds = [42, 123, 999]
        self.scorer.models = []
        train_data = lgb.Dataset(X, label=y)

        for seed in seeds:
            params = {
                "objective": "regression",
                "metric": "l2",
                "learning_rate": 0.05,
                "num_leaves": 15,
                "max_depth": 4,
                "verbosity": -1,
                "seed": seed,
            }
            # Train a smaller model suited for small active learning sets
            booster = lgb.train(params, train_data, num_boost_round=100)
            booster.objective_type = "regression"
            self.scorer.models.append(booster)

        # 3. Fit quantile regressors for aleatoric uncertainty
        quantiles = [0.05, 0.95]
        for q in quantiles:
            q_params = {
                "objective": "quantile",
                "alpha": q,
                "learning_rate": 0.05,
                "num_leaves": 15,
                "max_depth": 4,
                "verbosity": -1,
                "seed": 42,
            }
            q_booster = lgb.train(q_params, train_data, num_boost_round=100)
            q_booster.objective_type = "quantile"
            self.scorer.models.append(q_booster)

        if self.scorer.models:
            self.scorer.model = self.scorer.models[0]

        # 4. Train MLP Sequence Model
        X_seq_list = []
        for pair, _, _ in self.labeled_pool:
            f_emb = self.scorer.transformer.get_embeddings(pair.forward.sequence)
            r_emb = self.scorer.transformer.get_embeddings(pair.reverse.sequence)
            X_seq_list.append(np.concatenate([f_emb, r_emb]))
        X_seq = np.array(X_seq_list, dtype=np.float32)

        self.scorer.mlp = NumPyMLPRegressor(input_dim=32, hidden_dim=16)
        self.scorer.mlp.fit(X_seq, y)

        # 5. Fit Platt Calibration parameters
        raw_preds = []
        for booster in self.scorer.models:
            if getattr(booster, "objective_type", "regression") != "quantile":
                raw_preds.append(booster.predict(X))

        if hasattr(self.scorer, "mlp") and self.scorer.mlp is not None:
            mlp_preds = self.scorer.mlp.predict(X_seq)
            raw_preds.append(mlp_preds)

        mean_raw_preds = np.mean(raw_preds, axis=0)

        # Platt A & B gradient descent solver
        A, B = -1.0, 0.0
        lr = 0.05
        clamped = np.clip(mean_raw_preds, -20.0, 20.0)
        for _ in range(300):
            p = 1.0 / (1.0 + np.exp(A * clamped + B))
            grad_A = np.mean((p - y) * clamped)
            grad_B = np.mean(p - y)
            A += lr * grad_A
            B += lr * grad_B

        self.scorer.platt_a = float(A)
        self.scorer.platt_b = float(B)
        logger.info(
            f"Retraining complete. Platt platt_a: {self.scorer.platt_a:.4f}, platt_b: {self.scorer.platt_b:.4f}"
        )
