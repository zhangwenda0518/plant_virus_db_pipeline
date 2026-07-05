"""Federated & Continual Learning engine for PrimerForge.

Implements four publication-grade components that enable PrimerForge to
incorporate new experimental data without catastrophic forgetting and to
aggregate learning across distributed lab deployments without raw data sharing:

  1. **FisherInformationEstimator**
     Computes the diagonal of the empirical Fisher Information Matrix (FIM)
     for the NumPy MLP and MultiTaskAmpHead parameters using a dataset of
     primer features and outcomes. The diagonal FIM approximates the curvature
     of the loss landscape around the current parameter values.

  2. **ElasticWeightConsolidation (EWC)**
     Consolidates learned knowledge by penalizing updates to parameters that
     are important for previous tasks (high Fisher value). The penalty term is:
         L_EWC = λ/2 · Σ_i  F_i (θ_i − θ*_i)²
     where F_i is the Fisher importance and θ*_i is the anchor (old) parameter
     value. This prevents catastrophic forgetting during continual fine-tuning.
     Reference: Kirkpatrick et al. 2017, PNAS.

  3. **ExperienceReplayBuffer**
     A fixed-capacity ring buffer that stores (feature_vec, success_label,
     ct_target, yield_target, melt_target) tuples. Uses reservoir sampling
     (Vitter's Algorithm R) so that the buffer maintains a statistically
     uniform random sample of all seen examples regardless of arrival order.
     Reference: Vitter 1985, ACM TOMS.

  4. **OnlinePlattCalibrator**
     Streams updates to the Platt sigmoid calibration parameters (platt_a,
     platt_b) using stochastic gradient descent on binary cross-entropy loss.
     Warm-starts from the existing calibration, enabling incremental
     recalibration as new wet-lab outcomes arrive without full retraining.

  5. **FederatedAverager**
     Implements Federated Averaging (FedAvg) for the NumPy MLP and
     MultiTaskAmpHead weight matrices. Accepts serialized weight dictionaries
     from multiple lab deployments and returns a weighted average model —
     enabling collaborative learning without any raw data exchange.
     Reference: McMahan et al. 2017, AISTATS.

  6. **ContinualLearner**
     Top-level orchestrator composing all four components. Provides the public
     API used by MLScorer: ``update_from_new_data()`` and ``federated_merge()``.

All operations are in pure NumPy — no external ML frameworks required.
"""

import copy
import json
import numpy as np
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.continual_learner")


# ---------------------------------------------------------------------------
# 1. Fisher Information Estimator
# ---------------------------------------------------------------------------


class FisherInformationEstimator:
    """Estimates the diagonal of the empirical Fisher Information Matrix.

    For a model with parameters θ and loss L(θ; x, y), the empirical FIM
    diagonal at sample (x, y) is:

        F_i ≈ (∂L/∂θ_i)²

    averaged over the calibration dataset. High F_i means parameter θ_i is
    critical for accurate predictions — EWC will protect these parameters.

    Attributes
    ----------
    fisher_mlp : Dict mapping MLP weight name → Fisher diagonal (numpy array).
    fisher_mt  : Dict mapping MultiTaskAmpHead weight name → Fisher diagonal.
    n_samples  : Number of samples used to estimate the FIM.
    """

    def __init__(self) -> None:
        self.fisher_mlp: Dict[str, np.ndarray] = {}
        self.fisher_mt: Dict[str, np.ndarray] = {}
        self.n_samples: int = 0

    def estimate(
        self,
        mlp: Any,
        multitask_head: Any,
        X: np.ndarray,
        y_success: np.ndarray,
        y_ct: Optional[np.ndarray] = None,
        y_yield: Optional[np.ndarray] = None,
        y_melt: Optional[np.ndarray] = None,
    ) -> None:
        """Estimates FIM diagonal for MLP and MultiTaskAmpHead parameters.

        Uses squared gradients of the loss w.r.t. each weight as the diagonal
        Fisher approximation, averaged over the calibration dataset.

        Args:
            mlp:            NumPyMLPRegressor instance.
            multitask_head: MultiTaskAmpHead instance.
            X:              Feature matrix (N, 38).
            y_success:      Binary success labels (N,) ∈ [0, 1].
            y_ct:           Ct value targets (N,) — optional.
            y_yield:        Yield targets (N,) — optional.
            y_melt:         Melt targets (N,) — optional.
        """
        N = len(X)
        self.n_samples = N

        # Accumulate squared gradients for MLP
        fisher_w1 = np.zeros_like(mlp.w1, dtype=np.float64)
        fisher_b1 = np.zeros_like(mlp.b1, dtype=np.float64)
        fisher_w2 = np.zeros_like(mlp.w2, dtype=np.float64)
        fisher_b2 = np.zeros_like(mlp.b2, dtype=np.float64)

        # Accumulate squared gradients for MultiTaskAmpHead trunk + output heads
        fisher_tl1W = np.zeros_like(multitask_head.trunk_l1.W, dtype=np.float64)
        fisher_tl2W = np.zeros_like(multitask_head.trunk_l2.W, dtype=np.float64)
        fisher_ctW = np.zeros_like(multitask_head.ct_out.W, dtype=np.float64)
        fisher_yyW = np.zeros_like(multitask_head.yield_out.W, dtype=np.float64)
        fisher_mmW = np.zeros_like(multitask_head.melt_out.W, dtype=np.float64)

        for i in range(N):
            x_i = X[i]
            y_i = float(y_success[i])

            # ── MLP Fisher: MSE loss w.r.t. w1, b1, w2, b2 ──────────
            # Handle 2D biases: b1=(1,hidden), b2=(1,1) → flatten for scalar ops
            w2_flat = mlp.w2.flatten()  # (hidden,)
            b1_flat = mlp.b1.flatten()  # (hidden,)
            b2_scalar = float(mlp.b2.flatten()[0])
            x_mlp = x_i[: mlp.w1.shape[0]]  # MLP uses first 32 features

            pre_h = x_mlp @ mlp.w1 + b1_flat  # (hidden,)
            h = np.maximum(0.0, pre_h)  # (hidden,)
            pred = float(np.dot(h, w2_flat) + b2_scalar)

            d_loss = 2.0 * (pred - y_i)
            dw2 = d_loss * h  # (hidden,)
            db2 = np.array([d_loss])
            dh = d_loss * w2_flat  # (hidden,)
            dh_pre = dh * (pre_h > 0)
            dw1 = np.outer(x_mlp, dh_pre)
            db1 = dh_pre

            fisher_w1 += dw1**2
            fisher_b1 += db1.reshape(mlp.b1.shape) ** 2
            fisher_w2 += (
                dw2.reshape(mlp.w2.shape)
            ) ** 2  # reshape (hidden,) → (hidden,1)
            fisher_b2 += db2**2

            # ── MultiTaskAmpHead Fisher: from multitask loss ──────────
            if y_ct is not None and y_yield is not None and y_melt is not None:
                ct_t, yy_t, mm_t = float(y_ct[i]), float(y_yield[i]), float(y_melt[i])
            else:
                # Fallback: use success label to proxy Ct target
                ct_t = 15.0 + (1.0 - y_i) * 25.0
                yy_t, mm_t = y_i, 1.0

            # Run backward on multitask head to get gradients
            multitask_head.backward(x_i, ct_t, yy_t, mm_t)

            fisher_tl1W += multitask_head.trunk_l1.dW.astype(np.float64) ** 2
            fisher_tl2W += multitask_head.trunk_l2.dW.astype(np.float64) ** 2
            fisher_ctW += multitask_head.ct_out.dW.astype(np.float64) ** 2
            fisher_yyW += multitask_head.yield_out.dW.astype(np.float64) ** 2
            fisher_mmW += multitask_head.melt_out.dW.astype(np.float64) ** 2

        # Average over samples
        self.fisher_mlp = {
            "w1": (fisher_w1 / N).astype(np.float32),
            "b1": (fisher_b1 / N).astype(np.float32),
            "w2": (fisher_w2 / N).astype(np.float32),
            "b2": (fisher_b2 / N).astype(np.float32),
        }
        self.fisher_mt = {
            "trunk_l1_W": (fisher_tl1W / N).astype(np.float32),
            "trunk_l2_W": (fisher_tl2W / N).astype(np.float32),
            "ct_out_W": (fisher_ctW / N).astype(np.float32),
            "yield_out_W": (fisher_yyW / N).astype(np.float32),
            "melt_out_W": (fisher_mmW / N).astype(np.float32),
        }
        logger.info(f"Fisher FIM estimated on {N} samples.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_samples": self.n_samples,
            "fisher_mlp": {k: v.tolist() for k, v in self.fisher_mlp.items()},
            "fisher_mt": {k: v.tolist() for k, v in self.fisher_mt.items()},
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.n_samples = int(data.get("n_samples", 0))
        self.fisher_mlp = {
            k: np.array(v, dtype=np.float32)
            for k, v in data.get("fisher_mlp", {}).items()
        }
        self.fisher_mt = {
            k: np.array(v, dtype=np.float32)
            for k, v in data.get("fisher_mt", {}).items()
        }


# ---------------------------------------------------------------------------
# 2. Elastic Weight Consolidation
# ---------------------------------------------------------------------------


class ElasticWeightConsolidation:
    """Prevents catastrophic forgetting via Fisher-weighted parameter anchoring.

    Stores the anchor parameters θ* (model weights after training on Task A)
    and the Fisher diagonals F. When fine-tuning on Task B, adds the EWC
    penalty to the loss:

        L_EWC(θ) = L_B(θ) + λ/2 · Σ_i F_i (θ_i − θ*_i)²

    This constrains updates towards high-Fisher parameters, preserving
    knowledge from Task A while still allowing Task B learning.

    Attributes
    ----------
    lambda_ewc : EWC regularization strength.
    anchor_mlp : Snapshot of MLP weight arrays at anchor point.
    anchor_mt  : Snapshot of MultiTaskAmpHead weight arrays at anchor point.
    fisher     : FisherInformationEstimator instance.
    """

    def __init__(self, lambda_ewc: float = 500.0) -> None:
        """Initializes EWC.

        Args:
            lambda_ewc: Regularization strength. Higher = stronger protection
                        of old task knowledge. Typical range: [100, 5000].
        """
        self.lambda_ewc = lambda_ewc
        self.anchor_mlp: Dict[str, np.ndarray] = {}
        self.anchor_mt: Dict[str, np.ndarray] = {}
        self.fisher = FisherInformationEstimator()
        self._anchored = False

    def anchor(self, mlp: Any, multitask_head: Any) -> None:
        """Saves the current model parameters as the EWC anchor (θ*).

        Should be called immediately after training on the base task,
        before any fine-tuning on new data begins.

        Args:
            mlp:            NumPyMLPRegressor instance.
            multitask_head: MultiTaskAmpHead instance.
        """
        self.anchor_mlp = {
            "w1": mlp.w1.copy(),
            "b1": mlp.b1.copy(),
            "w2": mlp.w2.copy(),
            "b2": mlp.b2.copy(),
        }
        self.anchor_mt = {
            "trunk_l1_W": multitask_head.trunk_l1.W.copy(),
            "trunk_l2_W": multitask_head.trunk_l2.W.copy(),
            "ct_out_W": multitask_head.ct_out.W.copy(),
            "yield_out_W": multitask_head.yield_out.W.copy(),
            "melt_out_W": multitask_head.melt_out.W.copy(),
        }
        self._anchored = True
        logger.info("EWC: anchor parameters saved.")

    def compute_penalty(self, mlp: Any, multitask_head: Any) -> float:
        """Computes the EWC penalty for current model parameters.

        Args:
            mlp:            Current NumPyMLPRegressor.
            multitask_head: Current MultiTaskAmpHead.

        Returns:
            float: L_EWC = λ/2 · Σ_i F_i (θ_i − θ*_i)²
        """
        if not self._anchored or not self.fisher.fisher_mlp:
            return 0.0

        penalty = 0.0

        # MLP contribution
        for name, anchor_w in self.anchor_mlp.items():
            fisher_w = self.fisher.fisher_mlp.get(name)
            if fisher_w is None:
                continue
            current_w = getattr(mlp, name)
            penalty += float(np.sum(fisher_w * (current_w - anchor_w) ** 2))

        # MultiTaskAmpHead contribution
        mt_params = {
            "trunk_l1_W": multitask_head.trunk_l1.W,
            "trunk_l2_W": multitask_head.trunk_l2.W,
            "ct_out_W": multitask_head.ct_out.W,
            "yield_out_W": multitask_head.yield_out.W,
            "melt_out_W": multitask_head.melt_out.W,
        }
        for name, anchor_w in self.anchor_mt.items():
            fisher_w = self.fisher.fisher_mt.get(name)
            if fisher_w is None:
                continue
            current_w = mt_params[name]
            penalty += float(np.sum(fisher_w * (current_w - anchor_w) ** 2))

        return self.lambda_ewc * 0.5 * penalty

    def compute_ewc_gradients_mlp(self, mlp: Any) -> Dict[str, np.ndarray]:
        """Computes EWC gradient contributions for MLP parameters.

        Returns:
            Dict[str, ndarray]: Gradient addend for each MLP parameter name.
        """
        if not self._anchored or not self.fisher.fisher_mlp:
            return {}
        grads = {}
        for name, anchor_w in self.anchor_mlp.items():
            fisher_w = self.fisher.fisher_mlp.get(name)
            if fisher_w is None:
                continue
            current_w = getattr(mlp, name)
            grads[name] = self.lambda_ewc * fisher_w * (current_w - anchor_w)
        return grads

    def compute_ewc_gradients_mt(self, multitask_head: Any) -> Dict[str, np.ndarray]:
        """Computes EWC gradient contributions for MultiTaskAmpHead parameters.

        Returns:
            Dict[str, ndarray]: Gradient addend for each tracked weight matrix.
        """
        if not self._anchored or not self.fisher.fisher_mt:
            return {}
        mt_params = {
            "trunk_l1_W": multitask_head.trunk_l1.W,
            "trunk_l2_W": multitask_head.trunk_l2.W,
            "ct_out_W": multitask_head.ct_out.W,
            "yield_out_W": multitask_head.yield_out.W,
            "melt_out_W": multitask_head.melt_out.W,
        }
        grads = {}
        for name, anchor_w in self.anchor_mt.items():
            fisher_w = self.fisher.fisher_mt.get(name)
            if fisher_w is None:
                continue
            grads[name] = self.lambda_ewc * fisher_w * (mt_params[name] - anchor_w)
        return grads

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lambda_ewc": self.lambda_ewc,
            "_anchored": self._anchored,
            "anchor_mlp": {k: v.tolist() for k, v in self.anchor_mlp.items()},
            "anchor_mt": {k: v.tolist() for k, v in self.anchor_mt.items()},
            "fisher": self.fisher.to_dict(),
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.lambda_ewc = float(data.get("lambda_ewc", 500.0))
        self._anchored = bool(data.get("_anchored", False))
        self.anchor_mlp = {
            k: np.array(v, dtype=np.float32)
            for k, v in data.get("anchor_mlp", {}).items()
        }
        self.anchor_mt = {
            k: np.array(v, dtype=np.float32)
            for k, v in data.get("anchor_mt", {}).items()
        }
        self.fisher.from_dict(data.get("fisher", {}))


# ---------------------------------------------------------------------------
# 3. Experience Replay Buffer
# ---------------------------------------------------------------------------


class ExperienceReplayBuffer:
    """Fixed-capacity ring buffer with reservoir sampling (Vitter's Algorithm R).

    Stores (feature_vec, success, ct, yield_, melt) tuples and serves
    statistically unbiased mini-batches for replay during continual learning.

    Reservoir sampling guarantees that after M insertions into a buffer of
    capacity C, every incoming sample has equal probability C/M of being
    retained — regardless of arrival order.

    Attributes
    ----------
    capacity   : Maximum buffer size.
    n_seen     : Total number of examples seen since buffer creation.
    _buffer    : Internal deque storing the retained samples.
    """

    def __init__(self, capacity: int = 1000) -> None:
        """Initializes the replay buffer.

        Args:
            capacity: Maximum number of samples to retain. Older samples
                      are probabilistically replaced via reservoir sampling.
        """
        self.capacity = capacity
        self.n_seen = 0
        self._buffer: deque = deque(maxlen=capacity)
        self._rng = np.random.RandomState(seed=42)

    def add(
        self,
        x: np.ndarray,
        success: float,
        ct: float,
        yield_: float,
        melt: float,
    ) -> None:
        """Adds a new sample using reservoir sampling.

        With probability min(1, capacity/n_seen), the sample is retained
        in the buffer (replacing a random existing sample if full).

        Args:
            x:       Feature vector (38,).
            success: Binary success label ∈ [0, 1].
            ct:      Ct value target.
            yield_:  Endpoint yield target.
            melt:    Melt peak count target.
        """
        self.n_seen += 1
        entry = (x.copy(), float(success), float(ct), float(yield_), float(melt))

        if len(self._buffer) < self.capacity:
            # Buffer not yet full — always accept
            self._buffer.append(entry)
        else:
            # Reservoir sampling: replace random existing entry with prob capacity/n_seen
            j = int(self._rng.randint(0, self.n_seen))
            if j < self.capacity:
                # Replace entry at position j
                buf_list = list(self._buffer)
                buf_list[j] = entry
                self._buffer = deque(buf_list, maxlen=self.capacity)

    def add_batch(
        self,
        X: np.ndarray,
        y_success: np.ndarray,
        y_ct: np.ndarray,
        y_yield: np.ndarray,
        y_melt: np.ndarray,
    ) -> None:
        """Adds a batch of samples to the buffer.

        Args:
            X:         Feature matrix (N, 38).
            y_success: Success labels (N,).
            y_ct:      Ct targets (N,).
            y_yield:   Yield targets (N,).
            y_melt:    Melt targets (N,).
        """
        for i in range(len(X)):
            self.add(
                X[i],
                float(y_success[i]),
                float(y_ct[i]),
                float(y_yield[i]),
                float(y_melt[i]),
            )

    def sample(
        self, n: int
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """Samples a random mini-batch from the buffer.

        Args:
            n: Number of samples to draw (with replacement if n > buffer size).

        Returns:
            Tuple (X, y_success, y_ct, y_yield, y_melt) or None if buffer is empty.
        """
        if len(self._buffer) == 0:
            return None

        buf = list(self._buffer)
        n_actual = min(n, len(buf))
        idx = self._rng.choice(len(buf), size=n_actual, replace=(n > len(buf)))
        selected = [buf[i] for i in idx]

        X = np.array([s[0] for s in selected], dtype=np.float32)
        y_succ = np.array([s[1] for s in selected], dtype=np.float32)
        y_ct = np.array([s[2] for s in selected], dtype=np.float32)
        y_yld = np.array([s[3] for s in selected], dtype=np.float32)
        y_melt = np.array([s[4] for s in selected], dtype=np.float32)
        return X, y_succ, y_ct, y_yld, y_melt

    def __len__(self) -> int:
        return len(self._buffer)

    def to_dict(self) -> Dict[str, Any]:
        buf = list(self._buffer)
        return {
            "capacity": self.capacity,
            "n_seen": self.n_seen,
            "buffer_X": [e[0].tolist() for e in buf],
            "buffer_success": [e[1] for e in buf],
            "buffer_ct": [e[2] for e in buf],
            "buffer_yield": [e[3] for e in buf],
            "buffer_melt": [e[4] for e in buf],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.capacity = int(data.get("capacity", 1000))
        self.n_seen = int(data.get("n_seen", 0))
        self._buffer = deque(maxlen=self.capacity)
        xs = data.get("buffer_X", [])
        succs = data.get("buffer_success", [])
        cts = data.get("buffer_ct", [])
        yields = data.get("buffer_yield", [])
        melts = data.get("buffer_melt", [])
        for i in range(len(xs)):
            self._buffer.append(
                (
                    np.array(xs[i], dtype=np.float32),
                    float(succs[i]),
                    float(cts[i]),
                    float(yields[i]),
                    float(melts[i]),
                )
            )


# ---------------------------------------------------------------------------
# 4. Online Platt Calibrator
# ---------------------------------------------------------------------------


class OnlinePlattCalibrator:
    """Streaming sigmoid calibration via stochastic gradient on binary cross-entropy.

    Updates platt_a and platt_b from new (raw_score, success_label) pairs using
    mini-batch SGD on:
        BCE(a, b; s, y) = −[y log σ(a·s+b) + (1−y) log(1 − σ(a·s+b))]

    Warm-starts from the current calibration parameters so online updates
    incrementally improve without discarding existing calibration.

    Attributes
    ----------
    a  : Current platt_a (scale parameter).
    b  : Current platt_b (shift parameter).
    lr : Learning rate for SGD updates.
    """

    def __init__(self, a: float = -1.0, b: float = 0.0, lr: float = 0.01) -> None:
        self.a = a
        self.b = b
        self.lr = lr
        self._n_updates = 0

    def _sigmoid(self, z: float) -> float:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))

    def update(self, raw_scores: np.ndarray, labels: np.ndarray) -> float:
        """Runs one mini-batch SGD step on the calibration parameters.

        Args:
            raw_scores: Uncalibrated model scores (N,).
            labels:     Binary success labels (N,) ∈ {0, 1}.

        Returns:
            float: Mean binary cross-entropy loss for this batch.
        """
        N = len(raw_scores)
        total_loss = 0.0
        da = 0.0
        db = 0.0

        for i in range(N):
            s = float(raw_scores[i])
            y = float(labels[i])
            z = self.a * s + self.b
            p = self._sigmoid(z)

            # BCE loss
            eps = 1e-8
            total_loss += -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))

            # Gradients: d_BCE/d_a = (p-y)*s, d_BCE/d_b = (p-y)
            grad = p - y
            da += grad * s
            db += grad

        # Average gradient step
        self.a -= self.lr * da / N
        self.b -= self.lr * db / N
        self._n_updates += 1

        return total_loss / N

    def calibrate(self, raw_score: float) -> float:
        """Calibrates a single raw score to a probability.

        Args:
            raw_score: Uncalibrated ensemble prediction.

        Returns:
            float: Calibrated probability ∈ [0.01, 0.99].
        """
        p = self._sigmoid(self.a * raw_score + self.b)
        return float(max(0.01, min(0.99, p)))

    def to_dict(self) -> Dict[str, Any]:
        return {"a": self.a, "b": self.b, "lr": self.lr, "n_updates": self._n_updates}

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.a = float(data.get("a", -1.0))
        self.b = float(data.get("b", 0.0))
        self.lr = float(data.get("lr", 0.01))
        self._n_updates = int(data.get("n_updates", 0))


# ---------------------------------------------------------------------------
# 5. Federated Averager
# ---------------------------------------------------------------------------


class FederatedAverager:
    """Weighted Federated Averaging (FedAvg) for NumPy MLP + MultiTaskAmpHead.

    Merges weight dictionaries from multiple lab deployments without requiring
    raw data exchange. Each lab serializes its model weights and contributes
    a sample count (weight). The global model is the weighted average:

        θ_global = Σ_k (n_k / N_total) · θ_k

    where n_k is the number of training samples at lab k.

    Reference: McMahan et al. 2017, "Communication-Efficient Learning of Deep
    Networks from Decentralized Data", AISTATS.
    """

    @staticmethod
    def average_mlp_weights(
        weight_dicts: List[Dict[str, Any]],
        sample_counts: List[int],
    ) -> Dict[str, np.ndarray]:
        """Computes weighted average of MLP weight dictionaries.

        Args:
            weight_dicts:  List of MLP to_dict() outputs from each lab.
            sample_counts: Number of training samples per lab.

        Returns:
            Dict[str, np.ndarray]: Federated-averaged MLP weights.
        """
        total = sum(sample_counts)
        if total == 0 or not weight_dicts:
            return {}

        averaged: Dict[str, np.ndarray] = {}
        for key in weight_dicts[0]:
            try:
                stacked = np.stack(
                    [np.array(d[key], dtype=np.float64) for d in weight_dicts]
                )
                weights = np.array(sample_counts, dtype=np.float64) / total
                averaged[key] = np.sum(
                    stacked * weights.reshape(-1, *([1] * (stacked.ndim - 1))), axis=0
                ).astype(np.float32)
            except Exception as e:
                logger.warning(f"FedAvg: skipping key '{key}': {e}")
        return averaged

    @staticmethod
    def average_multitask_weights(
        weight_dicts: List[Dict[str, Any]],
        sample_counts: List[int],
    ) -> Dict[str, Any]:
        """Computes weighted average of MultiTaskAmpHead to_dict() outputs.

        Args:
            weight_dicts:  List of MultiTaskAmpHead to_dict() outputs.
            sample_counts: Number of training samples per lab.

        Returns:
            Dict: Merged MultiTaskAmpHead weight dict compatible with from_dict().
        """
        total = sum(sample_counts)
        if total == 0 or not weight_dicts:
            return {}

        weights = np.array(sample_counts, dtype=np.float64) / total
        result: Dict[str, Any] = {}

        # Identify numeric-tensor keys (skip scalar metadata)
        scalar_keys = {"w_ct", "w_yield", "w_melt", "t"}
        tensor_layer_keys = [
            "trunk_l1",
            "trunk_ln1",
            "trunk_l2",
            "trunk_ln2",
            "ct_h1",
            "ct_out",
            "yield_h1",
            "yield_out",
            "melt_h1",
            "melt_out",
        ]

        for layer_key in tensor_layer_keys:
            if layer_key not in weight_dicts[0]:
                continue
            result[layer_key] = {}
            for sub_key in weight_dicts[0][layer_key]:
                try:
                    stacked = np.stack(
                        [
                            np.array(d[layer_key][sub_key], dtype=np.float64)
                            for d in weight_dicts
                        ]
                    )
                    avg = np.sum(
                        stacked * weights.reshape(-1, *([1] * (stacked.ndim - 1))),
                        axis=0,
                    )
                    result[layer_key][sub_key] = avg.astype(np.float32).tolist()
                except Exception as e:
                    logger.warning(f"FedAvg: skipping {layer_key}.{sub_key}: {e}")

        # Copy scalar metadata from the largest contributor
        max_lab = int(np.argmax(sample_counts))
        for sk in scalar_keys:
            if sk in weight_dicts[max_lab]:
                result[sk] = weight_dicts[max_lab][sk]

        return result

    @staticmethod
    def apply_to_mlp(mlp: Any, averaged_weights: Dict[str, np.ndarray]) -> None:
        """Applies federated-averaged weights directly to an MLP instance."""
        for name, w in averaged_weights.items():
            if hasattr(mlp, name):
                setattr(mlp, name, w.copy())

    @staticmethod
    def apply_to_multitask(
        multitask_head: Any, averaged_weights: Dict[str, Any]
    ) -> None:
        """Applies federated-averaged weights to a MultiTaskAmpHead instance."""
        multitask_head.from_dict(averaged_weights)


# ---------------------------------------------------------------------------
# 6. ContinualLearner — Top-Level Orchestrator
# ---------------------------------------------------------------------------


class ContinualLearner:
    """Orchestrates all continual and federated learning components.

    This is the top-level API used by MLScorer to:

    1. ``anchor()``            — Snapshot current weights and estimate Fisher FIM.
    2. ``update_from_new_data()`` — Fine-tune on new wet-lab outcomes with EWC
                                   regularization + experience replay.
    3. ``federated_merge()``   — Merge weights from remote labs via FedAvg.
    4. ``recalibrate()``       — Stream-update Platt calibration on new outcomes.

    Attributes
    ----------
    ewc          : ElasticWeightConsolidation instance.
    replay       : ExperienceReplayBuffer instance.
    calibrator   : OnlinePlattCalibrator instance.
    n_replay     : Number of replay samples to mix in per new batch.
    fine_tune_lr : Learning rate for fine-tuning the MultiTaskAmpHead.
    """

    def __init__(
        self,
        lambda_ewc: float = 500.0,
        replay_capacity: int = 1000,
        platt_a: float = -1.0,
        platt_b: float = 0.0,
        n_replay: int = 32,
        fine_tune_lr: float = 2e-4,
    ) -> None:
        """Initializes the ContinualLearner.

        Args:
            lambda_ewc:      EWC regularization strength.
            replay_capacity: Maximum replay buffer capacity.
            platt_a:         Initial Platt scale (warm-started from MLScorer).
            platt_b:         Initial Platt shift (warm-started from MLScorer).
            n_replay:        Number of replay samples to interleave per update.
            fine_tune_lr:    Learning rate for fine-tuning gradient updates.
        """
        self.ewc = ElasticWeightConsolidation(lambda_ewc=lambda_ewc)
        self.replay = ExperienceReplayBuffer(capacity=replay_capacity)
        self.calibrator = OnlinePlattCalibrator(a=platt_a, b=platt_b)
        self.n_replay = n_replay
        self.fine_tune_lr = fine_tune_lr

    def anchor(
        self,
        mlp: Any,
        multitask_head: Any,
        X_anchor: np.ndarray,
        y_success: np.ndarray,
        y_ct: Optional[np.ndarray] = None,
        y_yield: Optional[np.ndarray] = None,
        y_melt: Optional[np.ndarray] = None,
    ) -> None:
        """Snapshots current weights and estimates Fisher FIM on anchor data.

        Call once after base training is complete, before any fine-tuning.

        Args:
            mlp:            NumPyMLPRegressor.
            multitask_head: MultiTaskAmpHead.
            X_anchor:       Representative calibration feature matrix (N, 38).
            y_success:      Binary success labels for Fisher estimation.
            y_ct/yield/melt: Multi-task targets for Fisher estimation (optional).
        """
        # Save anchor weights
        self.ewc.anchor(mlp, multitask_head)

        # Estimate Fisher on anchor dataset
        self.ewc.fisher.estimate(
            mlp, multitask_head, X_anchor, y_success, y_ct, y_yield, y_melt
        )

        # Pre-populate replay buffer with anchor data
        if y_ct is None:
            y_ct = np.clip(15.0 + (1.0 - y_success) * 25.0, 15.0, 40.0).astype(
                np.float32
            )
        if y_yield is None:
            y_yield = y_success.copy()
        if y_melt is None:
            y_melt = np.ones_like(y_success)
        self.replay.add_batch(X_anchor, y_success, y_ct, y_yield, y_melt)

        logger.info(
            f"ContinualLearner anchored. Replay buffer: {len(self.replay)} samples."
        )

    def update_from_new_data(
        self,
        multitask_head: Any,
        X_new: np.ndarray,
        y_success: np.ndarray,
        y_ct: Optional[np.ndarray] = None,
        y_yield: Optional[np.ndarray] = None,
        y_melt: Optional[np.ndarray] = None,
        raw_scores: Optional[np.ndarray] = None,
        epochs: int = 5,
    ) -> Dict[str, List[float]]:
        """Fine-tunes MultiTaskAmpHead on new data with EWC + replay.

        Interleaves new samples with replayed anchor samples to prevent
        catastrophic forgetting. Applies EWC gradient penalties on each step.

        Args:
            multitask_head: MultiTaskAmpHead to update in-place.
            X_new:          New primer feature matrix (N, 38).
            y_success:      New binary success labels (N,).
            y_ct:           New Ct targets (N,) — optional, inferred if None.
            y_yield:        New yield targets (N,) — optional.
            y_melt:         New melt targets (N,) — optional.
            raw_scores:     Raw ensemble scores for Platt recalibration (N,).
            epochs:         Number of fine-tuning epochs.

        Returns:
            Dict with keys 'new_losses', 'ewc_penalties', 'replay_losses'.
        """
        N = len(X_new)

        # Infer missing targets from success labels
        if y_ct is None:
            y_ct = np.clip(15.0 + (1.0 - y_success) * 25.0, 15.0, 40.0).astype(
                np.float32
            )
        if y_yield is None:
            y_yield = y_success.astype(np.float32)
        if y_melt is None:
            y_melt = np.ones(N, dtype=np.float32)

        new_losses: List[float] = []
        ewc_penalties: List[float] = []
        replay_losses: List[float] = []

        for epoch in range(epochs):
            # ── New data fine-tuning pass ─────────────────────────────
            idx = np.random.permutation(N)
            epoch_new_loss = 0.0
            epoch_ewc_pen = 0.0

            for i in idx:
                x_i = X_new[i]
                loss = multitask_head.backward(
                    x_i, float(y_ct[i]), float(y_yield[i]), float(y_melt[i])
                )

                # Apply EWC gradient regularization to trunk_l1 weights
                ewc_grads = self.ewc.compute_ewc_gradients_mt(multitask_head)
                if "trunk_l1_W" in ewc_grads:
                    multitask_head.trunk_l1.dW += ewc_grads["trunk_l1_W"]
                if "trunk_l2_W" in ewc_grads:
                    multitask_head.trunk_l2.dW += ewc_grads["trunk_l2_W"]

                # Apply gradient step
                multitask_head.t += 1
                for layer in [
                    multitask_head.trunk_l1,
                    multitask_head.trunk_l2,
                    multitask_head.ct_h1,
                    multitask_head.ct_out,
                    multitask_head.yield_h1,
                    multitask_head.yield_out,
                    multitask_head.melt_h1,
                    multitask_head.melt_out,
                ]:
                    layer.adam_step(self.fine_tune_lr, multitask_head.t)

                epoch_new_loss += loss
                epoch_ewc_pen += self.ewc.compute_penalty(
                    type(
                        "_DummyMLP", (), self.ewc.anchor_mlp
                    )(),  # dummy for penalty check
                    multitask_head,
                )

            new_losses.append(epoch_new_loss / max(N, 1))
            ewc_penalties.append(epoch_ewc_pen / max(N, 1))

            # ── Experience replay pass ────────────────────────────────
            replay_batch = self.replay.sample(self.n_replay)
            if replay_batch is not None:
                X_r, y_r_succ, y_r_ct, y_r_yld, y_r_melt = replay_batch
                replay_epoch_loss = 0.0
                for j in range(len(X_r)):
                    rl = multitask_head.backward(
                        X_r[j], float(y_r_ct[j]), float(y_r_yld[j]), float(y_r_melt[j])
                    )
                    replay_epoch_loss += rl
                    multitask_head.t += 1
                    for layer in [
                        multitask_head.trunk_l1,
                        multitask_head.trunk_l2,
                        multitask_head.ct_h1,
                        multitask_head.ct_out,
                        multitask_head.yield_h1,
                        multitask_head.yield_out,
                        multitask_head.melt_h1,
                        multitask_head.melt_out,
                    ]:
                        layer.adam_step(self.fine_tune_lr, multitask_head.t)
                replay_losses.append(replay_epoch_loss / max(len(X_r), 1))
            else:
                replay_losses.append(0.0)

        # Add new data to replay buffer for future updates
        self.replay.add_batch(X_new, y_success, y_ct, y_yield, y_melt)
        logger.info(
            f"ContinualLearner: fine-tuned {epochs} epochs on {N} new samples. "
            f"Replay buffer: {len(self.replay)} samples."
        )

        # ── Online Platt recalibration ────────────────────────────────
        if raw_scores is not None:
            bce_loss = self.calibrator.update(raw_scores, y_success)
            logger.info(
                f"Platt calibration updated. BCE loss: {bce_loss:.4f} | "
                f"a={self.calibrator.a:.4f}, b={self.calibrator.b:.4f}"
            )

        return {
            "new_losses": new_losses,
            "ewc_penalties": ewc_penalties,
            "replay_losses": replay_losses,
        }

    def federated_merge(
        self,
        mlp: Any,
        multitask_head: Any,
        remote_mlp_weights: List[Dict[str, Any]],
        remote_mt_weights: List[Dict[str, Any]],
        sample_counts: List[int],
        local_count: int = 1,
    ) -> None:
        """Merges remote lab weights into the local model via FedAvg.

        Combines the local model with remote weight snapshots using
        sample-count-weighted federated averaging. The merged weights
        are applied to the local model in-place.

        Args:
            mlp:                 Local NumPyMLPRegressor (modified in-place).
            multitask_head:      Local MultiTaskAmpHead (modified in-place).
            remote_mlp_weights:  List of to_dict() outputs from remote MLPs.
            remote_mt_weights:   List of to_dict() outputs from remote MultiTaskAmpHeads.
            sample_counts:       Training sample counts for each remote lab.
            local_count:         Local lab sample count (weight for local model).
        """
        # Include local model
        local_mlp_dict = {"w1": mlp.w1, "b1": mlp.b1, "w2": mlp.w2, "b2": mlp.b2}
        all_mlp = [local_mlp_dict] + remote_mlp_weights
        all_counts = [local_count] + sample_counts

        all_mt = [multitask_head.to_dict()] + remote_mt_weights

        avg_mlp = FederatedAverager.average_mlp_weights(all_mlp, all_counts)
        avg_mt = FederatedAverager.average_multitask_weights(all_mt, all_counts)

        FederatedAverager.apply_to_mlp(mlp, avg_mlp)
        FederatedAverager.apply_to_multitask(multitask_head, avg_mt)

        logger.info(
            f"Federated merge complete. Labs: {1 + len(remote_mlp_weights)}, "
            f"Total samples: {sum(all_counts)}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ewc": self.ewc.to_dict(),
            "replay": self.replay.to_dict(),
            "calibrator": self.calibrator.to_dict(),
            "n_replay": self.n_replay,
            "fine_tune_lr": self.fine_tune_lr,
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        if "ewc" in data:
            self.ewc.from_dict(data["ewc"])
        if "replay" in data:
            self.replay.from_dict(data["replay"])
        if "calibrator" in data:
            self.calibrator.from_dict(data["calibrator"])
        self.n_replay = int(data.get("n_replay", 32))
        self.fine_tune_lr = float(data.get("fine_tune_lr", 2e-4))
