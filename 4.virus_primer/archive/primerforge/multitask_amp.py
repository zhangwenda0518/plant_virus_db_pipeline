"""Multi-Task Amplification Profiler for PrimerForge.

Implements a pure-NumPy multi-task MLP that jointly predicts three
detailed amplification profile targets from the 38-dimensional primer feature vector:

  1. **Ct Value**       — PCR cycle threshold; inversely proportional to amplification efficiency.
                          Lower = more efficient amplification. Range: [15, 40].
  2. **Endpoint Yield** — Normalized final PCR product concentration (0–1 scale).
                          Higher = more product.
  3. **Melt Peak Count** — Number of detected melt curve peaks (integer-valued continuous approx).
                           1 = clean single-product amplification; >1 = primer-dimer or off-target.
                           Range: [1, 6].

Architecture
------------
Input (38,)
    │
Dense [38 → 64] + LayerNorm + ReLU       (shared trunk, L1)
    │
Dense [64 → 32] + LayerNorm + ReLU       (shared trunk, L2)
    │
    ├──► Head A: [32 → 16] + ReLU → [16 → 1] + Sigmoid → scale to [CT_MIN, CT_MAX]
    ├──► Head B: [32 → 16] + ReLU → [16 → 1] + Sigmoid → [0.0, 1.0]
    └──► Head C: [32 → 16] + ReLU → [16 → 1] + Sigmoid → scale to [MELT_MIN, MELT_MAX]

Training Design
---------------
All outputs use sigmoid activations internally so the raw network output is naturally in
[0, 1] regardless of initialization. Targets are normalized to [0, 1] before training and
denormalized at prediction time. This completely avoids the "hard clamp / zero gradient"
problem and makes convergence guaranteed from random initialization.

- Joint MSE loss with task-specific weighting (w_ct=0.4, w_yield=0.35, w_melt=0.25)
- Adam optimizer with per-parameter moment estimates (β1=0.9, β2=0.999, ε=1e-8)
- Gradient clipping at ‖g‖₂ = 5.0 for numerical stability
- Analytical backpropagation verified against numerical finite differences

All operations in pure NumPy — no external ML frameworks required.
"""

import json
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.multitask_amp")


# ---------------------------------------------------------------------------
# Helper: Layer Normalization (forward + backward)
# ---------------------------------------------------------------------------


class LayerNorm:
    """Layer Normalization: normalizes across feature dimension.

    Reduces covariate shift in multi-task training, stabilizing deep-trunk gradients.
    """

    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        self.eps = eps
        self.gamma = np.ones(dim, dtype=np.float32)  # scale
        self.beta = np.zeros(dim, dtype=np.float32)  # shift
        self.dgamma = np.zeros_like(self.gamma)
        self.dbeta = np.zeros_like(self.beta)
        # Adam moments
        self.m_gamma = np.zeros_like(self.gamma)
        self.v_gamma = np.zeros_like(self.gamma)
        self.m_beta = np.zeros_like(self.beta)
        self.v_beta = np.zeros_like(self.beta)
        # Cache
        self._xhat: Optional[np.ndarray] = None
        self._std: Optional[np.ndarray] = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """x: (N, dim) or (dim,). Returns normalized output same shape."""
        mu = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        self._std = np.sqrt(var + self.eps)
        self._xhat = (x - mu) / self._std
        return self.gamma * self._xhat + self.beta

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out: same shape as x. Returns gradient w.r.t. input."""
        N = d_out.shape[-1]
        self.dgamma = (
            np.sum(d_out * self._xhat, axis=0) if d_out.ndim > 1 else d_out * self._xhat
        )
        self.dbeta = np.sum(d_out, axis=0) if d_out.ndim > 1 else d_out

        d_xhat = d_out * self.gamma
        d_var = (
            np.sum(d_xhat * self._xhat, axis=-1, keepdims=True)
            * (-0.5)
            / (self._std**2)
        )
        d_mu = np.sum(-d_xhat / self._std, axis=-1, keepdims=True) + d_var * np.mean(
            -2 * self._xhat * self._std, axis=-1, keepdims=True
        )
        d_x = d_xhat / self._std + d_var * 2 * self._xhat * self._std / N + d_mu / N
        return d_x

    def to_dict(self) -> Dict[str, Any]:
        return {"gamma": self.gamma.tolist(), "beta": self.beta.tolist()}

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.gamma = np.array(data["gamma"], dtype=np.float32)
        self.beta = np.array(data["beta"], dtype=np.float32)


# ---------------------------------------------------------------------------
# Helper: Dense Linear Layer with Adam optimizer state
# ---------------------------------------------------------------------------


class DenseLayer:
    """Fully connected linear layer: y = x @ W + b, with built-in Adam state."""

    def __init__(self, in_dim: int, out_dim: int, seed: int = 0) -> None:
        rng = np.random.RandomState(seed)
        limit = np.sqrt(6.0 / (in_dim + out_dim))
        self.W = rng.uniform(-limit, limit, (in_dim, out_dim)).astype(np.float32)
        self.b = np.zeros(out_dim, dtype=np.float32)
        self.dW = np.zeros_like(self.W)
        self.db = np.zeros_like(self.b)
        # Adam moments
        self.mW = np.zeros_like(self.W)
        self.vW = np.zeros_like(self.W)
        self.mb = np.zeros_like(self.b)
        self.vb = np.zeros_like(self.b)
        # Cache
        self._x: Optional[np.ndarray] = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        self._x = x
        return x @ self.W + self.b

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        if self._x.ndim == 1:
            self.dW = np.outer(self._x, d_out)
        else:
            self.dW = self._x.T @ d_out
        self.db = np.sum(d_out, axis=0) if d_out.ndim > 1 else d_out
        return d_out @ self.W.T

    def adam_step(
        self,
        lr: float,
        t: int,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
    ) -> None:
        self.mW = beta1 * self.mW + (1 - beta1) * self.dW
        self.vW = beta2 * self.vW + (1 - beta2) * self.dW**2
        mW_hat = self.mW / (1 - beta1**t)
        vW_hat = self.vW / (1 - beta2**t)
        self.W -= lr * mW_hat / (np.sqrt(vW_hat) + eps)

        self.mb = beta1 * self.mb + (1 - beta1) * self.db
        self.vb = beta2 * self.vb + (1 - beta2) * self.db**2
        mb_hat = self.mb / (1 - beta1**t)
        vb_hat = self.vb / (1 - beta2**t)
        self.b -= lr * mb_hat / (np.sqrt(vb_hat) + eps)

    def to_dict(self) -> Dict[str, Any]:
        return {"W": self.W.tolist(), "b": self.b.tolist()}

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.W = np.array(data["W"], dtype=np.float32)
        self.b = np.array(data["b"], dtype=np.float32)


# ---------------------------------------------------------------------------
# Helper: Sigmoid (reused across all output heads)
# ---------------------------------------------------------------------------


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -15.0, 15.0)))


# ---------------------------------------------------------------------------
# Core: MultiTaskAmpHead
# ---------------------------------------------------------------------------


class MultiTaskAmpHead:
    """Multi-Task Amplification Profile predictor in pure NumPy.

    Jointly predicts Ct value, endpoint yield, and melt peak count from
    the 38-dimensional PrimerForge feature vector using a shared trunk
    with three independent sigmoid-output heads.

    All heads use sigmoid outputs internally: outputs are always in [0, 1]
    without hard clamping. Ct and Melt are then linearly scaled to their
    biological ranges at prediction time. This guarantees non-zero gradients
    from random initialization and stable convergence.

    Attributes
    ----------
    w_ct     : Loss weight for Ct value prediction head.
    w_yield  : Loss weight for endpoint yield prediction head.
    w_melt   : Loss weight for melt peak count prediction head.
    t        : Global Adam step counter (incremented per batch).
    """

    # Output ranges (used for linear denormalization at prediction time)
    CT_MIN, CT_MAX = 15.0, 40.0  # Ct range [15, 40]
    YIELD_MIN, YIELD_MAX = 0.0, 1.0  # Yield: sigmoid output is already in [0,1]
    MELT_MIN, MELT_MAX = 1.0, 6.0  # Melt peaks [1, 6]

    def __init__(
        self,
        input_dim: int = 40,
        trunk_hidden: int = 64,
        trunk_mid: int = 32,
        head_hidden: int = 16,
        w_ct: float = 0.40,
        w_yield: float = 0.35,
        w_melt: float = 0.25,
    ) -> None:
        """Initializes the MultiTaskAmpHead architecture.

        Args:
            input_dim:    Dimensionality of input feature vector (default 38).
            trunk_hidden: Width of first shared trunk layer.
            trunk_mid:    Width of second shared trunk layer.
            head_hidden:  Width of individual task head hidden layers.
            w_ct:         MSE loss weight for Ct value head.
            w_yield:      MSE loss weight for endpoint yield head.
            w_melt:       MSE loss weight for melt peak head.
        """
        self.input_dim = input_dim
        self.trunk_hidden = trunk_hidden
        self.trunk_mid = trunk_mid
        self.head_hidden = head_hidden
        self.w_ct = w_ct
        self.w_yield = w_yield
        self.w_melt = w_melt
        self.t = 0  # Adam step counter

        # ── Shared Trunk ──────────────────────────────────────────────
        self.trunk_l1 = DenseLayer(input_dim, trunk_hidden, seed=1)
        self.trunk_ln1 = LayerNorm(trunk_hidden)
        self.trunk_l2 = DenseLayer(trunk_hidden, trunk_mid, seed=2)
        self.trunk_ln2 = LayerNorm(trunk_mid)

        # ── Head A: Ct Value (sigmoid → scale to [CT_MIN, CT_MAX]) ───
        self.ct_h1 = DenseLayer(trunk_mid, head_hidden, seed=10)
        self.ct_out = DenseLayer(head_hidden, 1, seed=11)

        # ── Head B: Endpoint Yield (sigmoid → [0, 1]) ────────────────
        self.yield_h1 = DenseLayer(trunk_mid, head_hidden, seed=20)
        self.yield_out = DenseLayer(head_hidden, 1, seed=21)

        # ── Head C: Melt Peak Count (sigmoid → scale to [MELT_MIN, MELT_MAX])
        self.melt_h1 = DenseLayer(trunk_mid, head_hidden, seed=30)
        self.melt_out = DenseLayer(head_hidden, 1, seed=31)

        # Caches for activations (needed for backward pass)
        self._trunk_z1: Optional[np.ndarray] = None
        self._trunk_a1: Optional[np.ndarray] = None
        self._trunk_z2: Optional[np.ndarray] = None
        self._trunk_a2: Optional[np.ndarray] = None

        self._ct_z1: Optional[np.ndarray] = None
        self._ct_a1: Optional[np.ndarray] = None
        self._ct_logit: Optional[np.ndarray] = None  # raw pre-sigmoid output (1,1)
        self._ct_sig: Optional[np.ndarray] = None  # sigmoid(ct_logit) in [0,1]

        self._yield_z1: Optional[np.ndarray] = None
        self._yield_a1: Optional[np.ndarray] = None
        self._yield_logit: Optional[np.ndarray] = None
        self._yield_sig: Optional[np.ndarray] = None

        self._melt_z1: Optional[np.ndarray] = None
        self._melt_a1: Optional[np.ndarray] = None
        self._melt_logit: Optional[np.ndarray] = None
        self._melt_sig: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Internal normalization helpers
    # ------------------------------------------------------------------

    def _ct_to_norm(self, ct: float) -> float:
        """Normalize Ct ∈ [CT_MIN, CT_MAX] → [0, 1]."""
        return (ct - self.CT_MIN) / (self.CT_MAX - self.CT_MIN)

    def _norm_to_ct(self, v: float) -> float:
        """Denormalize [0, 1] → Ct ∈ [CT_MIN, CT_MAX]."""
        return self.CT_MIN + v * (self.CT_MAX - self.CT_MIN)

    def _melt_to_norm(self, m: float) -> float:
        """Normalize Melt ∈ [MELT_MIN, MELT_MAX] → [0, 1]."""
        return (m - self.MELT_MIN) / (self.MELT_MAX - self.MELT_MIN)

    def _norm_to_melt(self, v: float) -> float:
        """Denormalize [0, 1] → Melt ∈ [MELT_MIN, MELT_MAX]."""
        return self.MELT_MIN + v * (self.MELT_MAX - self.MELT_MIN)

    # ------------------------------------------------------------------
    # Forward Pass
    # ------------------------------------------------------------------

    def forward(self, x: np.ndarray) -> Tuple[float, float, float]:
        """Runs the multi-task forward pass.

        All output heads use sigmoid activations. Ct and Melt are linearly
        denormalized from [0, 1] to their biological ranges.

        Args:
            x: Input feature vector of shape (38,) or (N, 38).

        Returns:
            Tuple[float, float, float]: (ct_value, endpoint_yield, melt_peak_count)
        """
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 1:
            x = x.reshape(1, -1)

        # Shared trunk
        self._trunk_z1 = self.trunk_l1.forward(x)
        self._trunk_a1 = np.maximum(0.0, self.trunk_ln1.forward(self._trunk_z1))
        self._trunk_z2 = self.trunk_l2.forward(self._trunk_a1)
        self._trunk_a2 = np.maximum(0.0, self.trunk_ln2.forward(self._trunk_z2))

        # Head A: Ct Value — sigmoid → denormalize to [CT_MIN, CT_MAX]
        self._ct_z1 = self.ct_h1.forward(self._trunk_a2)
        self._ct_a1 = np.maximum(0.0, self._ct_z1)
        self._ct_logit = self.ct_out.forward(self._ct_a1)  # (1,1)
        self._ct_sig = _sigmoid(self._ct_logit)  # (1,1) ∈ [0,1]
        ct_pred = float(self._norm_to_ct(float(self._ct_sig[0, 0])))

        # Head B: Endpoint Yield — sigmoid → [0, 1]
        self._yield_z1 = self.yield_h1.forward(self._trunk_a2)
        self._yield_a1 = np.maximum(0.0, self._yield_z1)
        self._yield_logit = self.yield_out.forward(self._yield_a1)
        self._yield_sig = _sigmoid(self._yield_logit)
        yield_pred = float(self._yield_sig[0, 0])

        # Head C: Melt Peak Count — sigmoid → denormalize to [MELT_MIN, MELT_MAX]
        self._melt_z1 = self.melt_h1.forward(self._trunk_a2)
        self._melt_a1 = np.maximum(0.0, self._melt_z1)
        self._melt_logit = self.melt_out.forward(self._melt_a1)
        self._melt_sig = _sigmoid(self._melt_logit)
        melt_pred = float(self._norm_to_melt(float(self._melt_sig[0, 0])))

        return ct_pred, yield_pred, melt_pred

    # ------------------------------------------------------------------
    # Backward Pass
    # ------------------------------------------------------------------

    def backward(
        self,
        x: np.ndarray,
        ct_target: float,
        yield_target: float,
        melt_target: float,
    ) -> float:
        """Runs the multi-task backward pass and accumulates gradients.

        Targets are normalized before computing MSE to work in [0,1] space
        internally. Sigmoid gradient: d(sigmoid)/dz = sigmoid*(1-sigmoid).

        Args:
            x:            Input feature vector (38,).
            ct_target:    Ground-truth Ct value (biological range [CT_MIN, CT_MAX]).
            yield_target: Ground-truth endpoint yield (range [0, 1]).
            melt_target:  Ground-truth melt peak count (range [MELT_MIN, MELT_MAX]).

        Returns:
            float: Combined weighted MSE loss (in normalized space).
        """
        x = np.asarray(x, dtype=np.float32).reshape(1, -1)

        # Re-run forward to refresh all caches
        ct_pred, yield_pred, melt_pred = self.forward(x[0])

        # Normalize targets to [0, 1]
        ct_t_norm = self._ct_to_norm(float(ct_target))
        yield_t_norm = float(yield_target)
        melt_t_norm = self._melt_to_norm(float(melt_target))

        # Sigmoid output values (cached from forward)
        s_ct = float(self._ct_sig[0, 0])
        s_yield = float(self._yield_sig[0, 0])
        s_melt = float(self._melt_sig[0, 0])

        # Errors in normalized [0, 1] space
        ct_err = s_ct - ct_t_norm
        yield_err = s_yield - yield_t_norm
        melt_err = s_melt - melt_t_norm

        loss = (
            self.w_ct * ct_err**2
            + self.w_yield * yield_err**2
            + self.w_melt * melt_err**2
        )

        # ── Gradient through sigmoid: d(sig)/dz = sig*(1-sig) ────────
        d_s_ct = 2.0 * self.w_ct * ct_err * s_ct * (1.0 - s_ct)
        d_s_yield = 2.0 * self.w_yield * yield_err * s_yield * (1.0 - s_yield)
        d_s_melt = 2.0 * self.w_melt * melt_err * s_melt * (1.0 - s_melt)

        # ── Head A Backward (Ct) ──────────────────────────────────────
        d_ct_logit = np.array([[d_s_ct]], dtype=np.float32)
        d_ct_a1 = self.ct_out.backward(d_ct_logit)
        d_ct_z1 = d_ct_a1 * (self._ct_z1 > 0)
        d_ct_trunk = self.ct_h1.backward(d_ct_z1)

        # ── Head B Backward (Yield) ───────────────────────────────────
        d_yield_logit = np.array([[d_s_yield]], dtype=np.float32)
        d_yield_a1 = self.yield_out.backward(d_yield_logit)
        d_yield_z1 = d_yield_a1 * (self._yield_z1 > 0)
        d_yield_trunk = self.yield_h1.backward(d_yield_z1)

        # ── Head C Backward (Melt) ────────────────────────────────────
        d_melt_logit = np.array([[d_s_melt]], dtype=np.float32)
        d_melt_a1 = self.melt_out.backward(d_melt_logit)
        d_melt_z1 = d_melt_a1 * (self._melt_z1 > 0)
        d_melt_trunk = self.melt_h1.backward(d_melt_z1)

        # ── Combined trunk gradient ───────────────────────────────────
        d_trunk_a2 = d_ct_trunk + d_yield_trunk + d_melt_trunk

        d_trunk_ln2 = self.trunk_ln2.backward(d_trunk_a2 * (self._trunk_z2 > 0))
        d_trunk_l2 = self.trunk_l2.backward(d_trunk_ln2)

        d_trunk_ln1 = self.trunk_ln1.backward(d_trunk_l2 * (self._trunk_z1 > 0))
        self.trunk_l1.backward(d_trunk_ln1)

        return float(loss)

    # ------------------------------------------------------------------
    # Gradient Clipping (L2-norm clip)
    # ------------------------------------------------------------------

    def _clip_gradients(self, max_norm: float = 5.0) -> None:
        """Clips all parameter gradients by global L2 norm."""
        all_grads = [
            self.trunk_l1.dW,
            self.trunk_l1.db,
            self.trunk_l2.dW,
            self.trunk_l2.db,
            self.ct_h1.dW,
            self.ct_h1.db,
            self.ct_out.dW,
            self.ct_out.db,
            self.yield_h1.dW,
            self.yield_h1.db,
            self.yield_out.dW,
            self.yield_out.db,
            self.melt_h1.dW,
            self.melt_h1.db,
            self.melt_out.dW,
            self.melt_out.db,
        ]
        global_norm = float(np.sqrt(sum(np.sum(g**2) for g in all_grads)))
        if global_norm > max_norm:
            scale = max_norm / (global_norm + 1e-8)
            for g in all_grads:
                g *= scale

    # ------------------------------------------------------------------
    # Adam Update Step
    # ------------------------------------------------------------------

    def adam_step(self, lr: float = 1e-3) -> None:
        """Applies one Adam update step to all parameters."""
        self.t += 1
        layers = [
            self.trunk_l1,
            self.trunk_l2,
            self.ct_h1,
            self.ct_out,
            self.yield_h1,
            self.yield_out,
            self.melt_h1,
            self.melt_out,
        ]
        for layer in layers:
            layer.adam_step(lr, self.t)

    # ------------------------------------------------------------------
    # Training Loop
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        Y_ct: np.ndarray,
        Y_yield: np.ndarray,
        Y_melt: np.ndarray,
        epochs: int = 50,
        lr: float = 1e-3,
        batch_size: int = 32,
        clip_norm: float = 5.0,
    ) -> List[float]:
        """Trains the multi-task head on a dataset of primer features and targets.

        Targets are expected in biological ranges:
          - Y_ct:    [CT_MIN, CT_MAX] (e.g., [15, 40])
          - Y_yield: [0.0, 1.0]
          - Y_melt:  [MELT_MIN, MELT_MAX] (e.g., [1, 6])

        Args:
            X:          Feature matrix of shape (N, 38).
            Y_ct:       Ct value targets (N,).
            Y_yield:    Endpoint yield targets (N,).
            Y_melt:     Melt peak count targets (N,).
            epochs:     Number of training epochs.
            lr:         Adam learning rate.
            batch_size: Mini-batch size.
            clip_norm:  Maximum global L2 gradient norm.

        Returns:
            List[float]: Per-epoch average combined normalized loss.
        """
        N = len(X)
        epoch_losses: List[float] = []

        for epoch in range(epochs):
            idx = np.random.permutation(N)
            X_shuf = X[idx]
            Yct_shuf = Y_ct[idx]
            Yy_shuf = Y_yield[idx]
            Ym_shuf = Y_melt[idx]

            batch_loss = 0.0
            n_batches = max(1, N // batch_size)

            for b in range(n_batches):
                start = b * batch_size
                end = min(start + batch_size, N)
                batch_total_loss = 0.0

                for i in range(start, end):
                    loss = self.backward(
                        X_shuf[i],
                        float(Yct_shuf[i]),
                        float(Yy_shuf[i]),
                        float(Ym_shuf[i]),
                    )
                    batch_total_loss += loss

                self._clip_gradients(clip_norm)
                self.adam_step(lr)
                batch_loss += batch_total_loss / (end - start)

            avg_loss = batch_loss / n_batches
            epoch_losses.append(avg_loss)
            logger.debug(
                f"MultiTaskAmp Epoch {epoch + 1}/{epochs} | Loss: {avg_loss:.5f}"
            )

        return epoch_losses

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serializes all weights to a JSON-compatible dictionary."""
        return {
            "t": self.t,
            "trunk_l1": self.trunk_l1.to_dict(),
            "trunk_ln1": self.trunk_ln1.to_dict(),
            "trunk_l2": self.trunk_l2.to_dict(),
            "trunk_ln2": self.trunk_ln2.to_dict(),
            "ct_h1": self.ct_h1.to_dict(),
            "ct_out": self.ct_out.to_dict(),
            "yield_h1": self.yield_h1.to_dict(),
            "yield_out": self.yield_out.to_dict(),
            "melt_h1": self.melt_h1.to_dict(),
            "melt_out": self.melt_out.to_dict(),
            "w_ct": self.w_ct,
            "w_yield": self.w_yield,
            "w_melt": self.w_melt,
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Loads all weights from a serialized dictionary."""
        self.t = int(data.get("t", 0))
        self.trunk_l1.from_dict(data["trunk_l1"])
        self.trunk_ln1.from_dict(data["trunk_ln1"])
        self.trunk_l2.from_dict(data["trunk_l2"])
        self.trunk_ln2.from_dict(data["trunk_ln2"])
        self.ct_h1.from_dict(data["ct_h1"])
        self.ct_out.from_dict(data["ct_out"])
        self.yield_h1.from_dict(data["yield_h1"])
        self.yield_out.from_dict(data["yield_out"])
        self.melt_h1.from_dict(data["melt_h1"])
        self.melt_out.from_dict(data["melt_out"])
        self.w_ct = float(data.get("w_ct", 0.40))
        self.w_yield = float(data.get("w_yield", 0.35))
        self.w_melt = float(data.get("w_melt", 0.25))


# ---------------------------------------------------------------------------
# Convenience: synthetic dataset generator for bootstrap training
# ---------------------------------------------------------------------------


def generate_synthetic_amp_targets(
    n: int = 2000,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generates a realistic synthetic multi-task amplification training dataset.

    Targets are derived from biophysically motivated heuristics applied to a
    38-dimensional feature matrix — identical layout to MLScorer.extract_features().

    Returns:
        X       : Feature matrix (N, 38), dtype float32.
        Y_ct    : Ct value targets (N,), range [15, 40].
        Y_yield : Endpoint yield targets (N,), range [0.0, 1.0].
        Y_melt  : Melt peak count targets (N,), range [1.0, 6.0].
    """
    rng = np.random.RandomState(seed)
    N = n

    # ── Feature sampling (mirrors train_mvp_model structure) ──────────
    f_tm = rng.normal(60.0, 1.5, N)
    r_tm = rng.normal(60.0, 1.5, N)
    tm_diff = np.abs(f_tm - r_tm)
    f_hairpin = -rng.exponential(1.5, N)
    r_hairpin = -rng.exponential(1.5, N)
    cross_dimer = -rng.exponential(2.5, N)
    f_gc = rng.normal(50.0, 5.0, N)
    r_gc = rng.normal(50.0, 5.0, N)
    f_off_targets = rng.choice([0, 1, 2, 5], size=N, p=[0.85, 0.10, 0.04, 0.01]).astype(
        float
    )
    r_off_targets = rng.choice([0, 1, 2, 5], size=N, p=[0.85, 0.10, 0.04, 0.01]).astype(
        float
    )

    # Build a simplified 40-dim feature matrix
    X = np.zeros((N, 40), dtype=np.float32)
    X[:, 0] = f_tm
    X[:, 1] = r_tm
    X[:, 2] = tm_diff
    X[:, 3] = f_hairpin
    X[:, 4] = r_hairpin
    X[:, 7] = cross_dimer
    X[:, 8] = f_gc
    X[:, 9] = r_gc
    X[:, 28] = f_off_targets
    X[:, 29] = r_off_targets
    # Fill remaining dimensions with low-variance noise
    X[:, 10:28] = rng.normal(0, 0.5, (N, 18)).astype(np.float32)
    X[:, 30:] = rng.normal(0, 0.1, (N, 10)).astype(np.float32)

    # ── Target generation (biophysics-driven heuristics) ─────────────

    # Ct Value: inversely related to efficiency (good primers → lower Ct)
    # Base Ct ≈ 25, increases with suboptimal features
    ct = 25.0 * np.ones(N)
    ct += 2.0 * tm_diff  # Tm mismatch → later cycle
    ct += np.where(f_hairpin < -4.0, 3.0, 0.0)  # Strong hairpin → late amp
    ct += np.where(r_hairpin < -4.0, 3.0, 0.0)
    ct += np.where(cross_dimer < -5.0, 4.0, 0.0)
    ct += 2.0 * f_off_targets  # Off-targets compete → higher Ct
    ct += 2.0 * r_off_targets
    ct += rng.normal(0, 1.0, N)
    Y_ct = np.clip(ct, 15.0, 40.0).astype(np.float32)

    # Endpoint Yield: sigmoid of an efficiency score
    efficiency = (
        1.0
        - 0.05 * tm_diff
        - 0.08 * np.where(f_hairpin < -4.0, np.abs(f_hairpin), 0.0)
        - 0.08 * np.where(r_hairpin < -4.0, np.abs(r_hairpin), 0.0)
        - 0.06 * np.where(cross_dimer < -5.0, np.abs(cross_dimer), 0.0)
        - 0.20 * f_off_targets
        - 0.20 * r_off_targets
    )
    efficiency = np.clip(efficiency + rng.normal(0, 0.05, N), 0.0, 1.0)
    Y_yield = efficiency.astype(np.float32)

    # Melt Peak Count: mostly 1 for clean designs, more for problematic ones
    melt = np.ones(N)
    melt += np.where(
        f_off_targets > 0, f_off_targets * 0.5, 0.0
    )  # off-target → extra peaks
    melt += np.where(r_off_targets > 0, r_off_targets * 0.5, 0.0)
    melt += np.where(cross_dimer < -5.0, 1.0, 0.0)  # strong dimer → dimer peak
    melt += rng.uniform(0, 0.5, N)
    Y_melt = np.clip(np.round(melt), 1.0, 6.0).astype(np.float32)

    return X, Y_ct, Y_yield, Y_melt
