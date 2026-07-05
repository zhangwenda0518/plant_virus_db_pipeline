"""Biophysical Graph Neural Network (BioGNN) implemented in pure NumPy.

Models primer-template hybridizations as spatial molecular graphs and learns
to predict structural features like melting temperature (Tm) and dimer free energy (dG).
"""

import os
import json
import random
import numpy as np
from typing import Any, Dict, List, Tuple

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.gnn_biophysics")


def build_primer_graph(sequence: str) -> Tuple[np.ndarray, np.ndarray]:
    """Builds a spatial biophysical graph for a single primer sequence.

    Nodes represent bases. Edges represent backbone bonds and self-pairing matches.

    Returns:
        Tuple[X, A]:
            X: Node features array of shape (N, 8)
            A: Adjacency matrix of shape (N, N)
    """
    sequence = sequence.upper()
    N = len(sequence)
    if N == 0:
        return np.zeros((0, 8), dtype=np.float32), np.zeros((0, 0), dtype=np.float32)

    # 1. Node Features (N, 8)
    # Col 0-3: One-hot base encoding A, T, G, C
    # Col 4: Normalized position
    # Col 5: GC indicator
    # Col 6: Purine (A/G) indicator
    # Col 7: Bias feature (constant 1.0)
    X = np.zeros((N, 8), dtype=np.float32)
    base_map = {"A": 0, "T": 1, "G": 2, "C": 3}

    for i, base in enumerate(sequence):
        if base in base_map:
            X[i, base_map[base]] = 1.0
        X[i, 4] = float(i) / max(1.0, float(N - 1))
        X[i, 5] = 1.0 if base in "GC" else 0.0
        X[i, 6] = 1.0 if base in "AG" else 0.0
        X[i, 7] = 1.0

    # 2. Adjacency Matrix (N, N)
    A = np.zeros((N, N), dtype=np.float32)

    # Covalent backbone edges (adjacent nucleotides)
    for i in range(N - 1):
        A[i, i + 1] = 1.0
        A[i + 1, i] = 1.0

    # Self-complementarity base-pairing (hairpin loops)
    # Connect complementary bases A-T, G-C, G-T if distance > 3 bp
    complement_pairs = {
        ("A", "T"),
        ("T", "A"),
        ("G", "C"),
        ("C", "G"),
        ("G", "T"),
        ("T", "G"),
    }
    for i in range(N):
        for j in range(i + 4, N):
            if (sequence[i], sequence[j]) in complement_pairs:
                A[i, j] = 1.0
                A[j, i] = 1.0

    return X, A


def build_hybrid_graph(seq1: str, seq2: str) -> Tuple[np.ndarray, np.ndarray]:
    """Builds a spatial biophysical graph representing seq1 and seq2 hybridization.

    Finds the optimal antiparallel base-pairing alignment and connects paired nucleotides.

    Returns:
        Tuple[X, A]:
            X: Node features array of shape (N1 + N2, 8)
            A: Adjacency matrix of shape (N1 + N2, N1 + N2)
    """
    seq1 = seq1.upper()
    seq2 = seq2.upper()
    N1 = len(seq1)
    N2 = len(seq2)
    N = N1 + N2

    if N1 == 0 or N2 == 0:
        return np.zeros((N, 8), dtype=np.float32), np.zeros((N, N), dtype=np.float32)

    # 1. Node Features (N, 8)
    X = np.zeros((N, 8), dtype=np.float32)
    base_map = {"A": 0, "T": 1, "G": 2, "C": 3}

    # Sequence 1 nodes
    for i, base in enumerate(seq1):
        if base in base_map:
            X[i, base_map[base]] = 1.0
        X[i, 4] = float(i) / max(1.0, float(N1 - 1))
        X[i, 5] = 1.0 if base in "GC" else 0.0
        X[i, 6] = 1.0 if base in "AG" else 0.0
        X[i, 7] = 1.0

    # Sequence 2 nodes
    for i, base in enumerate(seq2):
        idx = N1 + i
        if base in base_map:
            X[idx, base_map[base]] = 1.0
        X[idx, 4] = float(i) / max(1.0, float(N2 - 1))
        X[idx, 5] = 1.0 if base in "GC" else 0.0
        X[idx, 6] = 1.0 if base in "AG" else 0.0
        X[idx, 7] = 1.0

    # 2. Adjacency Matrix (N, N)
    A = np.zeros((N, N), dtype=np.float32)

    # Covalent backbone edges for seq1
    for i in range(N1 - 1):
        A[i, i + 1] = 1.0
        A[i + 1, i] = 1.0

    # Covalent backbone edges for seq2
    for i in range(N2 - 1):
        idx1 = N1 + i
        idx2 = N1 + i + 1
        A[idx1, idx2] = 1.0
        A[idx2, idx1] = 1.0

    # Base-pairing alignment scan (antiparallel dimerization)
    # Find the shift that maximizes complementary base matches
    best_matches = []
    max_count = -1
    best_shift = 0

    complement_pairs = {
        ("A", "T"),
        ("T", "A"),
        ("G", "C"),
        ("C", "G"),
        ("G", "T"),
        ("T", "G"),
    }

    # Antiparallel sequence 2
    seq2_rev = seq2[::-1]

    # Shift seq2_rev across seq1
    # Shift ranges from -(N2 - 1) to N1 - 1
    for shift in range(-N2 + 1, N1):
        current_matches = []
        for i in range(N1):
            # Aligning index on seq2_rev: j_rev = i - shift
            j_rev = i - shift
            if 0 <= j_rev < N2:
                # Map back to original seq2 index (seq2_rev is reversed)
                j = N2 - 1 - j_rev
                if (seq1[i], seq2[j]) in complement_pairs:
                    current_matches.append((i, j))
        if len(current_matches) > max_count:
            max_count = len(current_matches)
            best_matches = current_matches

    # Add base pairing edges for the optimal dimerization shift
    for i, j in best_matches:
        idx1 = i
        idx2 = N1 + j
        A[idx1, idx2] = 1.0
        A[idx2, idx1] = 1.0

    return X, A


def compute_symmetric_normalized_adjacency(A: np.ndarray) -> np.ndarray:
    """Computes the symmetric normalized adjacency matrix: D^-1/2 * (A + I) * D^-1/2."""
    N = A.shape[0]
    if N == 0:
        return A
    tilde_A = A + np.eye(N, dtype=np.float32)
    degrees = np.sum(tilde_A, axis=1)
    degrees[degrees == 0.0] = 1.0

    deg_inv_sqrt = 1.0 / np.sqrt(degrees)
    deg_inv_sqrt_mat = np.diag(deg_inv_sqrt)

    return deg_inv_sqrt_mat @ tilde_A @ deg_inv_sqrt_mat


class GraphConvLayer:
    """Graph Convolutional Network (GCN) layer with analytical backpropagation."""

    def __init__(self, in_dim: int, out_dim: int) -> None:
        self.in_dim = in_dim
        self.out_dim = out_dim
        # Xavier initialization
        limit = np.sqrt(6.0 / (in_dim + out_dim))
        self.W = np.random.uniform(-limit, limit, (in_dim, out_dim)).astype(np.float32)
        self.dW = np.zeros_like(self.W)

        # Cache for backpropagation
        self.last_H: np.ndarray | None = None
        self.last_A_hat: np.ndarray | None = None
        self.last_Z: np.ndarray | None = None

    def forward(self, H: np.ndarray, A_hat: np.ndarray) -> np.ndarray:
        """H shape: (N, in_dim), A_hat shape: (N, N), Output: (N, out_dim)."""
        self.last_H = H
        self.last_A_hat = A_hat

        # Z = A_hat * H * W
        self.last_Z = A_hat @ H @ self.W

        # ReLU activation
        return np.maximum(0.0, self.last_Z)

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out shape: (N, out_dim), Returns gradient on input H."""
        # Gradient through ReLU: dZ = d_out * (Z > 0)
        d_Z = d_out * (self.last_Z > 0)

        # Gradients on weights: dW = H^T * A_hat^T * dZ
        # Since A_hat is symmetric, A_hat^T = A_hat
        self.dW = self.last_H.T @ (self.last_A_hat @ d_Z)

        # Gradient on input H: dH = A_hat * dZ * W^T
        d_H = self.last_A_hat @ d_Z @ self.W.T
        return d_H


class GraphMeanPool:
    """Readout layer aggregating node features via mean pooling."""

    def __init__(self) -> None:
        self.last_N = 0

    def forward(self, H: np.ndarray) -> np.ndarray:
        """H shape: (N, D), Output: (1, D)."""
        self.last_N = H.shape[0]
        if self.last_N == 0:
            return np.zeros((1, H.shape[1]), dtype=np.float32)
        return np.mean(H, axis=0, keepdims=True)

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out shape: (1, D), Returns gradient replicated for each node (N, D)."""
        if self.last_N == 0:
            return np.zeros((0, d_out.shape[1]), dtype=np.float32)
        return np.repeat(d_out / self.last_N, self.last_N, axis=0)


class BioGNN:
    """Biophysical Graph Neural Network for predicting DNA physical properties."""

    def __init__(self) -> None:
        # Layer dimensions
        # Node features (8) -> GCN1 (16) -> GCN2 (8) -> Pooling -> FFN1 (8) -> Output (2)
        self.conv1 = GraphConvLayer(8, 16)
        self.conv2 = GraphConvLayer(16, 8)
        self.pool = GraphMeanPool()

        # FFN dense layers
        self.W1 = np.random.normal(0, np.sqrt(2.0 / 8), (8, 8)).astype(np.float32)
        self.b1 = np.zeros(8, dtype=np.float32)

        self.W2 = np.random.normal(0, np.sqrt(2.0 / 8), (8, 2)).astype(np.float32)
        self.b2 = np.zeros(2, dtype=np.float32)

        # FFN gradients
        self.dW1 = np.zeros_like(self.W1)
        self.db1 = np.zeros_like(self.b1)
        self.dW2 = np.zeros_like(self.W2)
        self.db2 = np.zeros_like(self.b2)

        # Cache
        self.last_h_pool: np.ndarray | None = None
        self.last_z1: np.ndarray | None = None
        self.last_a1: np.ndarray | None = None

    def forward(self, X: np.ndarray, A: np.ndarray) -> np.ndarray:
        """Runs the spatial biophysical graph through the GNN pipeline.

        Returns predictions of shape (2,) representing [predicted_Tm, predicted_dG].
        """
        A_hat = compute_symmetric_normalized_adjacency(A)

        # 1. Graph Convolutions
        h1 = self.conv1.forward(X, A_hat)
        h2 = self.conv2.forward(h1, A_hat)

        # 2. Mean Readout
        self.last_h_pool = self.pool.forward(h2)

        # 3. Dense classification head
        self.last_z1 = self.last_h_pool @ self.W1 + self.b1
        self.last_a1 = np.maximum(0.0, self.last_z1)  # ReLU

        out = self.last_a1 @ self.W2 + self.b2
        return out[0]

    def backward(self, d_out: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Backpropagates gradient on prediction targets.

        d_out shape: (2,). Returns (dX, dA_dummy) gradients.
        """
        # Reshape to (1, 2)
        d_out_flat = d_out.reshape(1, 2)

        # Dense Layer 2 backward
        self.dW2 = self.last_a1.T @ d_out_flat
        self.db2 = np.sum(d_out_flat, axis=0)
        d_a1 = d_out_flat @ self.W2.T

        # ReLU dense activation backward
        d_z1 = d_a1 * (self.last_z1 > 0)

        # Dense Layer 1 backward
        self.dW1 = self.last_h_pool.T @ d_z1
        self.db1 = np.sum(d_z1, axis=0)
        d_pool = d_z1 @ self.W1.T

        # Mean Pooling backward
        d_conv2_out = self.pool.backward(d_pool)

        # Graph convolutions backward
        d_conv1_out = self.conv2.backward(d_conv2_out)
        d_X_in = self.conv1.backward(d_conv1_out)

        return d_X_in, np.zeros_like(d_X_in)

    def step(self, lr: float = 0.01) -> None:
        """Updates GNN parameter weights in-place using standard SGD."""
        # Graph convolution layers
        self.conv1.W -= lr * self.conv1.dW
        self.conv2.W -= lr * self.conv2.dW

        # Dense layers
        self.W1 -= lr * self.dW1
        self.b1 -= lr * self.db1
        self.W2 -= lr * self.dW2
        self.b2 -= lr * self.db2

    def train_on_pairs(
        self,
        sequences: List[Tuple[str, str]],
        targets: np.ndarray,
        epochs: int = 15,
        lr: float = 0.005,
    ) -> List[float]:
        """Trains the GNN directly on a list of sequence pair complexes."""
        losses = []
        N = len(sequences)
        if N == 0:
            return []

        for epoch in range(epochs):
            epoch_loss = 0.0

            # Shuffle indices
            indices = np.arange(N)
            np.random.shuffle(indices)

            for idx in indices:
                seq1, seq2 = sequences[idx]
                target = targets[idx]

                # Build graph
                X, A = build_hybrid_graph(seq1, seq2)
                if X.shape[0] == 0:
                    continue

                # Forward
                pred = self.forward(X, A)

                # Loss (MSE)
                loss = 0.5 * np.sum((pred - target) ** 2)
                epoch_loss += loss

                # Backward
                d_out = pred - target
                self.backward(d_out)

                # Gradient update step
                self.step(lr)

            epoch_loss /= N
            losses.append(epoch_loss)
            logger.debug(f"BioGNN Epoch {epoch+1}/{epochs} | Loss: {epoch_loss:.5f}")

        return losses

    def to_dict(self) -> Dict[str, Any]:
        """Serializes BioGNN weights to a JSON dictionary."""
        return {
            "conv1_W": self.conv1.W.tolist(),
            "conv2_W": self.conv2.W.tolist(),
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Loads BioGNN weights from a serialized JSON dictionary."""
        self.conv1.W = np.array(data["conv1_W"], dtype=np.float32)
        self.conv2.W = np.array(data["conv2_W"], dtype=np.float32)
        self.W1 = np.array(data["W1"], dtype=np.float32)
        self.b1 = np.array(data["b1"], dtype=np.float32)
        self.W2 = np.array(data["W2"], dtype=np.float32)
        self.b2 = np.array(data["b2"], dtype=np.float32)
