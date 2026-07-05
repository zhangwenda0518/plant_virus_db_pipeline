"""Custom DNA Transformer Encoder implemented in pure NumPy.

Includes Multi-Head Self-Attention, Layer Normalization, Positional Encodings,
Feed-Forward Networks, and a Masked Language Modeling prediction head.
Supports full analytic gradient calculation for backpropagation and training.
"""

import os
import json
import random
import numpy as np
from typing import Dict, List, Tuple, Any, Optional

from primerforge.utils import setup_logger

logger = setup_logger("primerforge.transformer")


class DNASequenceTokenizer:
    """Tokenizer for mapping DNA sequences to token IDs."""

    def __init__(self, max_len: int = 24) -> None:
        self.vocab = {
            "A": 0,
            "T": 1,
            "G": 2,
            "C": 3,
            "<pad>": 4,
            "<mask>": 5,
            "<cls>": 6,
            "<sep>": 7,
        }
        self.inv_vocab = {v: k for k, v in self.vocab.items()}
        self.max_len = max_len

    def encode(self, seq: str, add_special_tokens: bool = True) -> np.ndarray:
        """Encodes a DNA string sequence to an array of integer token IDs."""
        seq = seq.upper()
        tokens = []
        if add_special_tokens:
            tokens.append(self.vocab["<cls>"])

        for base in seq:
            if base in self.vocab:
                tokens.append(self.vocab[base])
            else:
                # Map degenerate bases to pad/mask or default A for simplicity
                tokens.append(self.vocab["A"])

        if add_special_tokens:
            tokens.append(self.vocab["<sep>"])

        # Padding
        if len(tokens) < self.max_len:
            tokens.extend([self.vocab["<pad>"]] * (self.max_len - len(tokens)))
        else:
            tokens = tokens[: self.max_len]

        return np.array(tokens, dtype=np.int32)

    def decode(self, ids: np.ndarray) -> str:
        """Decodes token IDs back to a DNA sequence string."""
        return "".join(self.inv_vocab.get(int(i), "?") for i in ids)


class AdamOptimizer:
    """Adam Optimizer for updating weights in pure NumPy."""

    def __init__(
        self,
        lr: float = 0.005,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
    ) -> None:
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m: Dict[int, np.ndarray] = {}
        self.v: Dict[int, np.ndarray] = {}
        self.t = 0

    def step(self, param: np.ndarray, grad: np.ndarray, param_id: int) -> None:
        """Updates a parameter in-place using its gradient and Adam history."""
        if param_id not in self.m:
            self.m[param_id] = np.zeros_like(param)
            self.v[param_id] = np.zeros_like(param)

        self.m[param_id] = self.beta1 * self.m[param_id] + (1 - self.beta1) * grad
        self.v[param_id] = self.beta2 * self.v[param_id] + (1 - self.beta2) * (grad**2)

        m_hat = self.m[param_id] / (1 - self.beta1**self.t)
        v_hat = self.v[param_id] / (1 - self.beta2**self.t)

        param -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)


def get_sinusoidal_positional_encoding(max_len: int, d_model: int) -> np.ndarray:
    """Computes fixed sinusoidal positional encodings."""
    pe = np.zeros((max_len, d_model), dtype=np.float32)
    position = np.arange(0, max_len, dtype=np.float32)[:, np.newaxis]
    div_term = np.exp(
        np.arange(0, d_model, 2, dtype=np.float32) * -(np.log(10000.0) / d_model)
    )

    pe[:, 0::2] = np.sin(position * div_term)
    pe[:, 1::2] = np.cos(position * div_term)
    return pe


class EmbeddingLayer:
    """Learnable token embedding layer with backpropagation."""

    def __init__(self, vocab_size: int, embed_dim: int) -> None:
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        # He/Xavier-like initialization
        self.W = np.random.normal(
            0, np.sqrt(2.0 / (vocab_size + embed_dim)), (vocab_size, embed_dim)
        ).astype(np.float32)
        self.dW = np.zeros_like(self.W)
        self.last_inputs: np.ndarray | None = None

    def forward(self, inputs: np.ndarray) -> np.ndarray:
        """Inputs shape: (B, T), Output shape: (B, T, D)."""
        self.last_inputs = inputs
        return self.W[inputs]

    def backward(self, d_out: np.ndarray) -> None:
        """d_out shape: (B, T, D). Computes gradient with respect to W."""
        self.dW.fill(0.0)
        B, T, D = d_out.shape
        # Accumulate gradients for each token index
        for b in range(B):
            for t in range(T):
                token_id = self.last_inputs[b, t]
                self.dW[token_id] += d_out[b, t]


class LayerNormLayer:
    """Layer Normalization layer with learnable gain (gamma) and bias (beta)."""

    def __init__(self, embed_dim: int, eps: float = 1e-5) -> None:
        self.embed_dim = embed_dim
        self.eps = eps
        self.gamma = np.ones(embed_dim, dtype=np.float32)
        self.beta = np.zeros(embed_dim, dtype=np.float32)
        self.dgamma = np.zeros_like(self.gamma)
        self.dbeta = np.zeros_like(self.beta)

        # Cache for backpropagation
        self.last_x: np.ndarray | None = None
        self.last_mean: np.ndarray | None = None
        self.last_var: np.ndarray | None = None
        self.last_x_hat: np.ndarray | None = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """x shape: (B, T, D), Output shape: (B, T, D)."""
        self.last_x = x
        self.last_mean = np.mean(x, axis=-1, keepdims=True)
        self.last_var = np.var(x, axis=-1, keepdims=True)
        self.last_x_hat = (x - self.last_mean) / np.sqrt(self.last_var + self.eps)
        return self.gamma * self.last_x_hat + self.beta

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out shape: (B, T, D), Returns gradient with respect to input dx."""
        self.dgamma = np.sum(d_out * self.last_x_hat, axis=(0, 1))
        self.dbeta = np.sum(d_out, axis=(0, 1))

        B, T, D = d_out.shape
        std_inv = 1.0 / np.sqrt(self.last_var + self.eps)

        # d_x_hat gradient
        dx_hat = d_out * self.gamma

        # Standard analytical backprop for LayerNorm
        dx = (
            (1.0 / D)
            * std_inv
            * (
                D * dx_hat
                - np.sum(dx_hat, axis=-1, keepdims=True)
                - self.last_x_hat
                * np.sum(dx_hat * self.last_x_hat, axis=-1, keepdims=True)
            )
        )
        return dx


class MultiHeadAttentionLayer:
    """Multi-Head Self-Attention layer with backpropagation."""

    def __init__(self, embed_dim: int, num_heads: int) -> None:
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        assert (
            self.head_dim * num_heads == embed_dim
        ), "embed_dim must be divisible by num_heads"

        # Parameters Q, K, V projections and Output projection
        scale = np.sqrt(1.0 / embed_dim)
        self.W_q = np.random.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
        self.b_q = np.zeros(embed_dim, dtype=np.float32)

        self.W_k = np.random.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
        self.b_k = np.zeros(embed_dim, dtype=np.float32)

        self.W_v = np.random.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
        self.b_v = np.zeros(embed_dim, dtype=np.float32)

        self.W_o = np.random.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
        self.b_o = np.zeros(embed_dim, dtype=np.float32)

        # Gradients
        self.dW_q = np.zeros_like(self.W_q)
        self.db_q = np.zeros_like(self.b_q)
        self.dW_k = np.zeros_like(self.W_k)
        self.db_k = np.zeros_like(self.b_k)
        self.dW_v = np.zeros_like(self.W_v)
        self.db_v = np.zeros_like(self.b_v)
        self.dW_o = np.zeros_like(self.W_o)
        self.db_o = np.zeros_like(self.b_o)

        # Backpropagation cache
        self.last_x: np.ndarray | None = None
        self.last_q: np.ndarray | None = None
        self.last_k: np.ndarray | None = None
        self.last_v: np.ndarray | None = None
        self.last_attn_weights: np.ndarray | None = None
        self.last_attn_scores: np.ndarray | None = None
        self.last_context: np.ndarray | None = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """x shape: (B, T, D). Computes Self-Attention output of shape (B, T, D)."""
        self.last_x = x
        B, T, D = x.shape
        H = self.num_heads
        D_k = self.head_dim

        # 1. Project Q, K, V
        # Reshape to (B*T, D) for fast gemm
        x_flat = x.reshape(B * T, D)
        q = (x_flat @ self.W_q + self.b_q).reshape(B, T, D)
        k = (x_flat @ self.W_k + self.b_k).reshape(B, T, D)
        v = (x_flat @ self.W_v + self.b_v).reshape(B, T, D)

        self.last_q = q
        self.last_k = k
        self.last_v = v

        # 2. Reshape to multi-head: (B, H, T, D_k)
        q_h = q.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)
        k_h = k.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)
        v_h = v.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)

        # 3. Scaled dot-product scores: (B, H, T, T)
        scores = (q_h @ k_h.transpose(0, 1, 3, 2)) / np.sqrt(D_k)
        self.last_attn_scores = scores

        # 4. Softmax over last axis
        # Subtract max for numerical stability
        scores_max = np.max(scores, axis=-1, keepdims=True)
        exp_scores = np.exp(scores - scores_max)
        attn_weights = exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)
        self.last_attn_weights = attn_weights

        # 5. Weighted values context: (B, H, T, D_k)
        context_h = attn_weights @ v_h

        # 6. Concat heads and project back to D
        context = context_h.transpose(0, 2, 1, 3).reshape(B, T, D)
        self.last_context = context

        out = context.reshape(B * T, D) @ self.W_o + self.b_o
        return out.reshape(B, T, D)

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out shape: (B, T, D). Computes gradients and returns input gradient dx."""
        B, T, D = d_out.shape
        H = self.num_heads
        D_k = self.head_dim

        # 1. Output projection gradients
        d_out_flat = d_out.reshape(B * T, D)
        context_flat = self.last_context.reshape(B * T, D)
        self.dW_o = context_flat.T @ d_out_flat
        self.db_o = np.sum(d_out_flat, axis=0)

        # Gradient backpropagated into context: (B, T, D)
        d_context = (d_out_flat @ self.W_o.T).reshape(B, T, D)

        # 2. Transpose context to multi-head: (B, H, T, D_k)
        d_context_h = d_context.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)

        q_h = self.last_q.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)
        k_h = self.last_k.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)
        v_h = self.last_v.reshape(B, T, H, D_k).transpose(0, 2, 1, 3)
        attn_weights = self.last_attn_weights

        # 3. Gradients through context = attn_weights @ v_h
        # d_attn_weights: (B, H, T, T)
        d_attn_weights = d_context_h @ k_h.transpose(
            0, 1, 3, 2
        )  # Wait, no! it is d_context_h @ v_h.T
        d_attn_weights = d_context_h @ v_h.transpose(0, 1, 3, 2)
        # d_v_h: (B, H, T, D_k)
        d_v_h = attn_weights.transpose(0, 1, 3, 2) @ d_context_h

        # 4. Gradient through Softmax: S = softmax(scores)
        # For each head, batch, position: d_scores = S * (d_S - sum(d_S * S, axis=-1))
        d_scores = attn_weights * (
            d_attn_weights
            - np.sum(d_attn_weights * attn_weights, axis=-1, keepdims=True)
        )

        # Scale back: scores = Q @ K.T / sqrt(D_k)
        d_scores_scaled = d_scores / np.sqrt(D_k)

        # 5. Gradients with respect to Q, K
        d_q_h = d_scores_scaled @ k_h
        d_k_h = d_scores_scaled.transpose(0, 1, 3, 2) @ q_h

        # 6. Reshape Q, K, V back to flat matrices of shape (B*T, D)
        d_q = d_q_h.transpose(0, 2, 1, 3).reshape(B * T, D)
        d_k = d_k_h.transpose(0, 2, 1, 3).reshape(B * T, D)
        d_v = d_v_h.transpose(0, 2, 1, 3).reshape(B * T, D)

        # 7. Gradients for Q, K, V projection parameters
        x_flat = self.last_x.reshape(B * T, D)
        self.dW_q = x_flat.T @ d_q
        self.db_q = np.sum(d_q, axis=0)

        self.dW_k = x_flat.T @ d_k
        self.db_k = np.sum(d_k, axis=0)

        self.dW_v = x_flat.T @ d_v
        self.db_v = np.sum(d_v, axis=0)

        # 8. Gradient with respect to input X
        dx_flat = d_q @ self.W_q.T + d_k @ self.W_k.T + d_v @ self.W_v.T
        return dx_flat.reshape(B, T, D)


class FeedForwardLayer:
    """Position-wise Feed-Forward Network layer with backpropagation."""

    def __init__(self, embed_dim: int, hidden_dim: int) -> None:
        self.embed_dim = embed_dim
        self.hidden_dim = hidden_dim

        # Initial weights & biases
        scale1 = np.sqrt(2.0 / embed_dim)
        scale2 = np.sqrt(2.0 / hidden_dim)
        self.W1 = np.random.normal(0, scale1, (embed_dim, hidden_dim)).astype(
            np.float32
        )
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)

        self.W2 = np.random.normal(0, scale2, (hidden_dim, embed_dim)).astype(
            np.float32
        )
        self.b2 = np.zeros(embed_dim, dtype=np.float32)

        self.dW1 = np.zeros_like(self.W1)
        self.db1 = np.zeros_like(self.b1)
        self.dW2 = np.zeros_like(self.W2)
        self.db2 = np.zeros_like(self.b2)

        # Cache
        self.last_x: np.ndarray | None = None
        self.last_z1: np.ndarray | None = None
        self.last_a1: np.ndarray | None = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """x shape: (B, T, D), Output shape: (B, T, D)."""
        self.last_x = x
        B, T, D = x.shape
        x_flat = x.reshape(B * T, D)

        self.last_z1 = x_flat @ self.W1 + self.b1
        self.last_a1 = np.maximum(0.0, self.last_z1)  # ReLU

        out_flat = self.last_a1 @ self.W2 + self.b2
        return out_flat.reshape(B, T, D)

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """d_out shape: (B, T, D), Returns gradient on input dx."""
        B, T, D = d_out.shape
        d_out_flat = d_out.reshape(B * T, D)

        # Second layer gradients
        self.dW2 = self.last_a1.T @ d_out_flat
        self.db2 = np.sum(d_out_flat, axis=0)

        # Backprop through linear layer 2
        d_a1 = d_out_flat @ self.W2.T

        # Backprop through ReLU
        d_z1 = d_a1 * (self.last_z1 > 0)

        # First layer gradients
        x_flat = self.last_x.reshape(B * T, D)
        self.dW1 = x_flat.T @ d_z1
        self.db1 = np.sum(d_z1, axis=0)

        # Input gradient
        dx_flat = d_z1 @ self.W1.T
        return dx_flat.reshape(B, T, D)


class TransformerEncoderBlock:
    """A complete single-layer Transformer Encoder Block with Residual and LayerNorm."""

    def __init__(self, embed_dim: int, num_heads: int, hidden_dim: int) -> None:
        self.attn = MultiHeadAttentionLayer(embed_dim, num_heads)
        self.ln1 = LayerNormLayer(embed_dim)
        self.ff = FeedForwardLayer(embed_dim, hidden_dim)
        self.ln2 = LayerNormLayer(embed_dim)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass with residual pre-LN or post-LN configuration (here using standard post-LN)."""
        # 1. Self Attention + Residual
        attn_out = self.attn.forward(x)
        x_ln1 = self.ln1.forward(x + attn_out)

        # 2. Feedforward + Residual
        ff_out = self.ff.forward(x_ln1)
        x_ln2 = self.ln2.forward(x_ln1 + ff_out)
        return x_ln2

    def backward(self, d_out: np.ndarray) -> np.ndarray:
        """Backward pass through FFN, LN2, Attention, LN1. Returns gradient on input."""
        # FFN block + LN2 backward
        d_ln2 = self.ln2.backward(d_out)
        d_ff_in = self.ff.backward(d_ln2)
        d_x_ln1 = d_ln2 + d_ff_in

        # Attention block + LN1 backward
        d_ln1 = self.ln1.backward(d_x_ln1)
        d_attn_in = self.attn.backward(d_ln1)
        d_x_in = d_ln1 + d_attn_in
        return d_x_in


class MLMHeadLayer:
    """Prediction head for Masked Language Modeling (linear projection to vocab)."""

    def __init__(self, embed_dim: int, vocab_size: int) -> None:
        self.embed_dim = embed_dim
        self.vocab_size = vocab_size
        scale = np.sqrt(2.0 / embed_dim)
        self.W = np.random.normal(0, scale, (embed_dim, vocab_size)).astype(np.float32)
        self.b = np.zeros(vocab_size, dtype=np.float32)

        self.dW = np.zeros_like(self.W)
        self.db = np.zeros_like(self.b)

        # Cache
        self.last_x: np.ndarray | None = None
        self.last_masked_positions: np.ndarray | None = None
        self.last_probs: np.ndarray | None = None

    def forward(self, x: np.ndarray, masked_positions: np.ndarray) -> np.ndarray:
        """Extracts states at masked positions and computes logits.

        x shape: (B, T, D)
        masked_positions: tuple of (batch_indices, seq_indices) indicating masked tokens
        Output shape: (num_masked, vocab_size)
        """
        self.last_masked_positions = masked_positions
        # Extract states: shape (num_masked, D)
        self.last_x = x[masked_positions]

        logits = self.last_x @ self.W + self.b

        # Softmax
        logits_max = np.max(logits, axis=-1, keepdims=True)
        exp_logits = np.exp(logits - logits_max)
        self.last_probs = exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)
        return self.last_probs

    def backward(self, targets: np.ndarray) -> np.ndarray:
        """targets shape: (num_masked,). Computes loss gradients and returns gradient on full input dx."""
        num_masked = len(targets)

        # Gradient with respect to logits: P - Y
        d_logits = self.last_probs.copy()
        d_logits[np.arange(num_masked), targets] -= 1.0
        # Average over batch scale
        d_logits /= num_masked

        # Gradients on weights
        self.dW = self.last_x.T @ d_logits
        self.db = np.sum(d_logits, axis=0)

        # Gradient on masked input states dx: (num_masked, D)
        d_x_masked = d_logits @ self.W.T
        return d_x_masked


class DNATransformerEncoder:
    """DNA Transformer Encoder pre-trained via self-supervised Masked Language Modeling."""

    def __init__(
        self,
        vocab_size: int = 8,
        embed_dim: int = 16,
        num_heads: int = 2,
        hidden_dim: int = 32,
        max_len: int = 24,
        pretrained_weights_path: Optional[str] = None,
    ) -> None:
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.max_len = max_len
        self.pretrained_loaded = False

        self.tokenizer = DNASequenceTokenizer(max_len=max_len)
        self.emb = EmbeddingLayer(vocab_size, embed_dim)
        self.pe = get_sinusoidal_positional_encoding(max_len, embed_dim)
        self.block = TransformerEncoderBlock(embed_dim, num_heads, hidden_dim)
        self.mlm_head = MLMHeadLayer(embed_dim, vocab_size)

        # Parameter indexing for Adam optimizer
        self.layers = [
            self.emb,
            self.block.attn,
            self.block.ff,
            self.block.ln1,
            self.block.ln2,
            self.mlm_head,
        ]

        # Load pre-trained weights if available
        if pretrained_weights_path is not None:
            if os.path.exists(pretrained_weights_path):
                try:
                    with open(pretrained_weights_path, "r") as f:
                        weights_data = json.load(f)
                    self.from_dict(weights_data)
                    self.pretrained_loaded = True
                    logger.info(
                        f"Successfully loaded pre-trained DNA Transformer weights from {pretrained_weights_path}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to load pre-trained DNA Transformer weights from {pretrained_weights_path}: {e}. Falling back to random initialization."
                    )
            else:
                logger.warning(
                    f"Pre-trained weights file not found at {pretrained_weights_path}. Running with random initialization."
                )

    def forward(self, token_ids: np.ndarray) -> np.ndarray:
        """Runs sequence of token IDs through the encoder. Returns shape (B, T, D)."""
        x = self.emb.forward(token_ids)
        # Add sinusoidal positional encoding
        x = x + self.pe[np.newaxis, :, :]
        # Run through encoder block
        out = self.block.forward(x)
        return out

    def get_embeddings(self, seq: str) -> np.ndarray:
        """Returns the mean-pooled sequence embedding for a single DNA sequence string."""
        tokens = self.tokenizer.encode(seq, add_special_tokens=True)
        # Add batch axis
        inputs = tokens[np.newaxis, :]
        states = self.forward(inputs)
        # Mean pool over all non-padding tokens
        non_pad_mask = tokens != self.tokenizer.vocab["<pad>"]
        valid_states = states[0, non_pad_mask]
        mean_embedding = np.mean(valid_states, axis=0)
        return mean_embedding

    def pretrain_on_sequences(
        self,
        sequences: List[str],
        epochs: int = 10,
        batch_size: int = 64,
        lr: float = 0.005,
    ) -> List[float]:
        """Pre-trains the model via Masked Language Modeling on a list of DNA sequences."""
        optimizer = AdamOptimizer(lr=lr)
        loss_history = []

        # Setup tokens dataset
        encoded_tokens = []
        for seq in sequences:
            encoded_tokens.append(self.tokenizer.encode(seq, add_special_tokens=True))
        dataset = np.array(encoded_tokens, dtype=np.int32)
        N = len(dataset)

        pad_token = self.tokenizer.vocab["<pad>"]
        cls_token = self.tokenizer.vocab["<cls>"]
        sep_token = self.tokenizer.vocab["<sep>"]
        mask_token = self.tokenizer.vocab["<mask>"]

        for epoch in range(epochs):
            # Shuffle
            indices = np.arange(N)
            np.random.shuffle(indices)
            dataset = dataset[indices]

            epoch_losses = []

            for start_idx in range(0, N, batch_size):
                end_idx = min(start_idx + batch_size, N)
                batch = dataset[start_idx:end_idx].copy()
                B, T = batch.shape

                # 1. Randomly mask 15% of non-special/non-padding tokens
                masked_positions_b = []
                masked_positions_t = []
                targets = []

                for b in range(B):
                    for t in range(T):
                        tok = batch[b, t]
                        if tok not in [pad_token, cls_token, sep_token]:
                            # 15% probability of masking
                            if random.random() < 0.15:
                                masked_positions_b.append(b)
                                masked_positions_t.append(t)
                                targets.append(tok)
                                batch[b, t] = mask_token

                if len(targets) == 0:
                    continue

                masked_positions = (
                    np.array(masked_positions_b),
                    np.array(masked_positions_t),
                )
                targets = np.array(targets, dtype=np.int32)

                # 2. Forward pass
                hidden_states = self.forward(batch)
                probs = self.mlm_head.forward(hidden_states, masked_positions)

                # 3. Compute loss
                num_masked = len(targets)
                loss = -np.mean(np.log(probs[np.arange(num_masked), targets] + 1e-12))
                epoch_losses.append(loss)

                # 4. Backward pass
                d_x_masked = self.mlm_head.backward(targets)

                # Reconstruct full dx gradient shape (B, T, D)
                d_hidden = np.zeros_like(hidden_states)
                d_hidden[masked_positions] = d_x_masked

                # Propagate back through block and embedding
                d_emb = self.block.backward(d_hidden)
                self.emb.backward(d_emb)

                # 5. Optimizer step
                optimizer.t += 1
                param_id = 0

                # MultiHeadAttention parameters
                attn = self.block.attn
                for p, gp in [
                    (attn.W_q, attn.dW_q),
                    (attn.b_q, attn.db_q),
                    (attn.W_k, attn.dW_k),
                    (attn.b_k, attn.db_k),
                    (attn.W_v, attn.dW_v),
                    (attn.b_v, attn.db_v),
                    (attn.W_o, attn.dW_o),
                    (attn.b_o, attn.db_o),
                ]:
                    optimizer.step(p, gp, param_id)
                    param_id += 1

                # Feedforward parameters
                ff = self.block.ff
                for p, gp in [
                    (ff.W1, ff.dW1),
                    (ff.b1, ff.db1),
                    (ff.W2, ff.dW2),
                    (ff.b2, ff.db2),
                ]:
                    optimizer.step(p, gp, param_id)
                    param_id += 1

                # LN parameters
                for ln in [self.block.ln1, self.block.ln2]:
                    for p, gp in [(ln.gamma, ln.dgamma), (ln.beta, ln.dbeta)]:
                        optimizer.step(p, gp, param_id)
                        param_id += 1

                # Embedding parameters
                optimizer.step(self.emb.W, self.emb.dW, param_id)
                param_id += 1

                # MLM Head parameters
                optimizer.step(self.mlm_head.W, self.mlm_head.dW, param_id)
                param_id += 1

            mean_loss = float(np.mean(epoch_losses)) if epoch_losses else 0.0
            loss_history.append(mean_loss)
            logger.info(
                f"MLM Pre-training Epoch {epoch+1}/{epochs} | Average Loss: {mean_loss:.4f}"
            )

        return loss_history

    def to_dict(self) -> Dict[str, Any]:
        """Serializes weights to a JSON-compatible dictionary."""
        return {
            "emb_W": self.emb.W.tolist(),
            "attn_W_q": self.block.attn.W_q.tolist(),
            "attn_b_q": self.block.attn.b_q.tolist(),
            "attn_W_k": self.block.attn.W_k.tolist(),
            "attn_b_k": self.block.attn.b_k.tolist(),
            "attn_W_v": self.block.attn.W_v.tolist(),
            "attn_b_v": self.block.attn.b_v.tolist(),
            "attn_W_o": self.block.attn.W_o.tolist(),
            "attn_b_o": self.block.attn.b_o.tolist(),
            "ff_W1": self.block.ff.W1.tolist(),
            "ff_b1": self.block.ff.b1.tolist(),
            "ff_W2": self.block.ff.W2.tolist(),
            "ff_b2": self.block.ff.b2.tolist(),
            "ln1_gamma": self.block.ln1.gamma.tolist(),
            "ln1_beta": self.block.ln1.beta.tolist(),
            "ln2_gamma": self.block.ln2.gamma.tolist(),
            "ln2_beta": self.block.ln2.beta.tolist(),
            "mlm_W": self.mlm_head.W.tolist(),
            "mlm_b": self.mlm_head.b.tolist(),
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Loads weights from a serialized dictionary with strict shape and key validation."""
        required_keys = [
            "emb_W",
            "attn_W_q",
            "attn_b_q",
            "attn_W_k",
            "attn_b_k",
            "attn_W_v",
            "attn_b_v",
            "attn_W_o",
            "attn_b_o",
            "ff_W1",
            "ff_b1",
            "ff_W2",
            "ff_b2",
            "ln1_gamma",
            "ln1_beta",
            "ln2_gamma",
            "ln2_beta",
            "mlm_W",
            "mlm_b",
        ]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required key '{key}' in weights dictionary")

        def check_shape(name: str, arr: np.ndarray, expected: Tuple[int, ...]) -> None:
            if arr.shape != expected:
                raise ValueError(
                    f"Shape mismatch for '{name}': expected {expected}, got {arr.shape}"
                )

        emb_W = np.array(data["emb_W"], dtype=np.float32)
        check_shape("emb_W", emb_W, (self.vocab_size, self.embed_dim))

        attn = self.block.attn
        attn_W_q = np.array(data["attn_W_q"], dtype=np.float32)
        attn_b_q = np.array(data["attn_b_q"], dtype=np.float32)
        attn_W_k = np.array(data["attn_W_k"], dtype=np.float32)
        attn_b_k = np.array(data["attn_b_k"], dtype=np.float32)
        attn_W_v = np.array(data["attn_W_v"], dtype=np.float32)
        attn_b_v = np.array(data["attn_b_v"], dtype=np.float32)
        attn_W_o = np.array(data["attn_W_o"], dtype=np.float32)
        attn_b_o = np.array(data["attn_b_o"], dtype=np.float32)

        check_shape("attn_W_q", attn_W_q, (self.embed_dim, self.embed_dim))
        check_shape("attn_b_q", attn_b_q, (self.embed_dim,))
        check_shape("attn_W_k", attn_W_k, (self.embed_dim, self.embed_dim))
        check_shape("attn_b_k", attn_b_k, (self.embed_dim,))
        check_shape("attn_W_v", attn_W_v, (self.embed_dim, self.embed_dim))
        check_shape("attn_b_v", attn_b_v, (self.embed_dim,))
        check_shape("attn_W_o", attn_W_o, (self.embed_dim, self.embed_dim))
        check_shape("attn_b_o", attn_b_o, (self.embed_dim,))

        ff = self.block.ff
        ff_W1 = np.array(data["ff_W1"], dtype=np.float32)
        ff_b1 = np.array(data["ff_b1"], dtype=np.float32)
        ff_W2 = np.array(data["ff_W2"], dtype=np.float32)
        ff_b2 = np.array(data["ff_b2"], dtype=np.float32)

        check_shape("ff_W1", ff_W1, (self.embed_dim, ff.hidden_dim))
        check_shape("ff_b1", ff_b1, (ff.hidden_dim,))
        check_shape("ff_W2", ff_W2, (ff.hidden_dim, self.embed_dim))
        check_shape("ff_b2", ff_b2, (self.embed_dim,))

        ln1_gamma = np.array(data["ln1_gamma"], dtype=np.float32)
        ln1_beta = np.array(data["ln1_beta"], dtype=np.float32)
        ln2_gamma = np.array(data["ln2_gamma"], dtype=np.float32)
        ln2_beta = np.array(data["ln2_beta"], dtype=np.float32)

        check_shape("ln1_gamma", ln1_gamma, (self.embed_dim,))
        check_shape("ln1_beta", ln1_beta, (self.embed_dim,))
        check_shape("ln2_gamma", ln2_gamma, (self.embed_dim,))
        check_shape("ln2_beta", ln2_beta, (self.embed_dim,))

        mlm_W = np.array(data["mlm_W"], dtype=np.float32)
        mlm_b = np.array(data["mlm_b"], dtype=np.float32)

        check_shape("mlm_W", mlm_W, (self.embed_dim, self.vocab_size))
        check_shape("mlm_b", mlm_b, (self.vocab_size,))

        # Apply weights after validation passes
        self.emb.W = emb_W
        attn.W_q = attn_W_q
        attn.b_q = attn_b_q
        attn.W_k = attn_W_k
        attn.b_k = attn_b_k
        attn.W_v = attn_W_v
        attn.b_v = attn_b_v
        attn.W_o = attn_W_o
        attn.b_o = attn_b_o
        ff.W1 = ff_W1
        ff.b1 = ff_b1
        ff.W2 = ff_W2
        ff.b2 = ff_b2
        self.block.ln1.gamma = ln1_gamma
        self.block.ln1.beta = ln1_beta
        self.block.ln2.gamma = ln2_gamma
        self.block.ln2.beta = ln2_beta
        self.mlm_head.W = mlm_W
        self.mlm_head.b = mlm_b

    def get_cls_embedding(self, seq: str) -> np.ndarray:
        """Returns the [CLS] token embedding for a single DNA primer sequence.

        The [CLS] token is at position 0 (prepended by the tokenizer). After
        transformer encoding, its hidden state captures global sequence context
        suitable for classification tasks (Devlin et al. 2019, NAACL-HLT).

        Args:
            seq: DNA sequence string (5'→3').

        Returns:
            np.ndarray: Shape (embed_dim,) = (16,). The [CLS] hidden state.
        """
        tokens = self.tokenizer.encode(seq, add_special_tokens=True)
        inputs = tokens[np.newaxis, :]  # (1, T)
        states = self.forward(inputs)  # (1, T, D)
        cls_embedding = states[0, 0, :]  # position 0 = [CLS]
        return cls_embedding.astype(np.float32)  # (16,)


# ---------------------------------------------------------------------------
# Fine-Tune Classification Head (Devlin 2019 BERT-style task fine-tuning)
# ---------------------------------------------------------------------------


class FineTuneClassificationHead:
    """2-layer MLP classification head on top of the [CLS] transformer embedding.

    Adds task-specific supervised fine-tuning on top of the MLM pre-trained
    DNATransformerEncoder, following the BERT fine-tuning paradigm:

        [CLS] embedding (16,)
            ↓
        Dense(16→8, ReLU) + Dropout(p=0.1, training only)
            ↓
        Dense(8→1, Sigmoid)
            ↓
        P(primer_success) ∈ (0.01, 0.99)

    Training uses Adam (Kingma & Ba 2014) with gradient clipping (‖g‖₂ ≤ 2.0)
    to stabilize fine-tuning of the shallow head without disturbing pre-trained
    encoder weights.

    Frozen layers (first 2 attention + embedding parameters) are not updated
    during fine-tuning to preserve MLM-learned representations.

    Scientific References:
        Devlin et al. (2019). BERT: Pre-training of Deep Bidirectional
        Transformers for Language Understanding. NAACL-HLT.
        doi:10.18653/v1/N19-1423

        Kingma & Ba (2014). Adam: A Method for Stochastic Optimization.
        ICLR 2015. arXiv:1412.6980.

    Attributes:
        W1: Dense weight matrix (16, 8).
        b1: Dense bias (8,).
        W2: Dense weight matrix (8, 1).
        b2: Dense bias (1,).
        lr: Adam learning rate.
        clip_norm: Gradient clipping threshold (‖g‖₂).
        dropout_rate: Dropout probability (applied to hidden layer during training).
        _n_updates: Number of fine-tuning parameter updates performed.
    """

    def __init__(
        self,
        input_dim: int = 16,
        hidden_dim: int = 8,
        lr: float = 1e-4,
        clip_norm: float = 2.0,
        dropout_rate: float = 0.1,
        seed: int = 42,
    ) -> None:
        """Initializes the FineTuneClassificationHead.

        Args:
            input_dim:    Dimensionality of [CLS] embedding (default 16 = embed_dim).
            hidden_dim:   Hidden layer size (default 8).
            lr:           Adam learning rate (default 1e-4, conservative for fine-tuning).
            clip_norm:    Max gradient ‖g‖₂ before clipping (default 2.0).
            dropout_rate: Dropout probability on hidden layer during training.
            seed:         NumPy random seed for reproducibility.
        """
        rng = np.random.RandomState(seed)

        # He initialization for ReLU layers (He et al. 2015)
        self.W1 = rng.normal(
            0, np.sqrt(2.0 / input_dim), (input_dim, hidden_dim)
        ).astype(np.float32)
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)
        self.W2 = rng.normal(0, np.sqrt(2.0 / hidden_dim), (hidden_dim, 1)).astype(
            np.float32
        )
        self.b2 = np.zeros(1, dtype=np.float32)

        self.lr = lr
        self.clip_norm = clip_norm
        self.dropout_rate = dropout_rate
        self._n_updates = 0

        # Adam state
        self._mW1 = np.zeros_like(self.W1)
        self._vW1 = np.zeros_like(self.W1)
        self._mb1 = np.zeros_like(self.b1)
        self._vb1 = np.zeros_like(self.b1)
        self._mW2 = np.zeros_like(self.W2)
        self._vW2 = np.zeros_like(self.W2)
        self._mb2 = np.zeros_like(self.b2)
        self._vb2 = np.zeros_like(self.b2)

        # Adam hyper-parameters (Kingma & Ba 2014)
        self._beta1 = 0.9
        self._beta2 = 0.999
        self._eps = 1e-8

        # Cache for backward pass
        self._last_cls: Optional[np.ndarray] = None
        self._last_h: Optional[np.ndarray] = None
        self._last_p: Optional[float] = None
        self._last_mask: Optional[np.ndarray] = None

    # ── Forward pass ──────────────────────────────────────────────────────

    @staticmethod
    def _sigmoid(z: float) -> float:
        return float(1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0))))

    def forward(
        self,
        cls_embedding: np.ndarray,
        training: bool = False,
    ) -> float:
        """Computes P(success) from a [CLS] embedding.

        Args:
            cls_embedding: Shape (16,) — [CLS] hidden state from transformer.
            training:      If True, applies dropout to hidden layer.

        Returns:
            float: P(success) ∈ [0.01, 0.99].
        """
        self._last_cls = cls_embedding.copy()

        # Layer 1: Dense + ReLU
        pre_h = cls_embedding @ self.W1 + self.b1  # (hidden_dim,)
        h = np.maximum(0.0, pre_h)  # ReLU

        # Dropout (Bernoulli mask, scaling factor 1/(1-p))
        if training and self.dropout_rate > 0.0:
            mask = (np.random.rand(*h.shape) > self.dropout_rate).astype(np.float32)
            h = h * mask / (1.0 - self.dropout_rate)
            self._last_mask = mask
        else:
            self._last_mask = np.ones_like(h)

        self._last_h = h.copy()
        self._last_pre_h = pre_h.copy()

        # Layer 2: Dense + Sigmoid
        logit = float(h @ self.W2.flatten() + self.b2[0])
        p = self._sigmoid(logit)
        self._last_p = p

        # Clamp to [0.01, 0.99] to prevent log(0)
        return float(max(0.01, min(0.99, p)))

    # ── Backward pass ─────────────────────────────────────────────────────

    def backward(
        self,
        cls_embedding: np.ndarray,
        label: float,
    ) -> Dict[str, np.ndarray]:
        """Computes gradients via BCE loss backpropagation.

        Loss: L = −[y log p + (1−y) log(1−p)]

        Args:
            cls_embedding: Shape (16,) — [CLS] embedding used in forward.
            label:         Ground-truth success label ∈ {0.0, 1.0}.

        Returns:
            Dict mapping weight name → gradient array.
        """
        p = self._last_p if self._last_p is not None else 0.5
        h = self._last_h if self._last_h is not None else np.zeros(self.b1.shape)
        pre_h = self._last_pre_h if hasattr(self, "_last_pre_h") else np.zeros_like(h)
        mask = self._last_mask if self._last_mask is not None else np.ones_like(h)

        # ∂L/∂logit = p - y (BCE + sigmoid combined gradient)
        d_logit = p - label

        # Layer 2 gradients
        dW2 = d_logit * h.reshape(-1, 1)  # (hidden_dim, 1)
        db2 = np.array([d_logit])

        # Gradient through Layer 2 → hidden
        d_h = d_logit * self.W2.flatten()  # (hidden_dim,)

        # Gradient through dropout
        d_h = d_h * mask / max(1.0 - self.dropout_rate, 1e-7)

        # Gradient through ReLU
        d_pre_h = d_h * (pre_h > 0).astype(np.float32)

        # Layer 1 gradients
        dW1 = np.outer(cls_embedding, d_pre_h)  # (input_dim, hidden_dim)
        db1 = d_pre_h

        return {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2}

    # ── Adam parameter update ─────────────────────────────────────────────

    def _adam_update(
        self,
        param: np.ndarray,
        grad: np.ndarray,
        m: np.ndarray,
        v: np.ndarray,
        t: int,
    ) -> None:
        """In-place Adam update for a single parameter tensor.

        Implements Adam (Kingma & Ba 2014):
            m_t = β₁ · m_{t-1} + (1-β₁) · g_t
            v_t = β₂ · v_{t-1} + (1-β₂) · g_t²
            m̂ = m_t / (1 - β₁^t)
            v̂ = v_t / (1 - β₂^t)
            θ_t = θ_{t-1} - α · m̂ / (√v̂ + ε)
        """
        m[:] = self._beta1 * m + (1 - self._beta1) * grad
        v[:] = self._beta2 * v + (1 - self._beta2) * (grad**2)
        m_hat = m / (1 - self._beta1**t)
        v_hat = v / (1 - self._beta2**t)
        param -= self.lr * m_hat / (np.sqrt(v_hat) + self._eps)

    def _clip_grad(self, grad: np.ndarray) -> np.ndarray:
        """Clips gradient by global ‖g‖₂ norm (Pascanu et al. 2013)."""
        norm = float(np.linalg.norm(grad))
        if norm > self.clip_norm:
            return grad * (self.clip_norm / norm)
        return grad

    def update(self, grads: Dict[str, np.ndarray]) -> None:
        """Applies Adam update with gradient clipping to all parameters.

        Args:
            grads: Output of backward() — dict of weight name → gradient.
        """
        self._n_updates += 1
        t = self._n_updates

        dW1 = self._clip_grad(grads["W1"])
        db1 = self._clip_grad(grads["b1"])
        dW2 = self._clip_grad(grads["W2"])
        db2 = self._clip_grad(grads["b2"])

        self._adam_update(self.W1, dW1, self._mW1, self._vW1, t)
        self._adam_update(self.b1, db1, self._mb1, self._vb1, t)
        self._adam_update(self.W2, dW2, self._mW2, self._vW2, t)
        self._adam_update(self.b2, db2, self._mb2, self._vb2, t)

    # ── Training loop ─────────────────────────────────────────────────────

    def fine_tune(
        self,
        transformer: "DNATransformerEncoder",
        sequences: List[str],
        labels: np.ndarray,
        epochs: int = 20,
        batch_size: int = 32,
    ) -> List[float]:
        """Fine-tunes the classification head on labeled primer data.

        The transformer encoder is kept frozen (no backprop into it).
        Only the FineTuneClassificationHead weights (W1, b1, W2, b2) are updated.

        Follows Devlin et al. (2019) recommendation: fine-tune only the task-
        specific head in early epochs; the encoder's representations are already
        well-calibrated from MLM pre-training.

        Args:
            transformer: Pre-trained DNATransformerEncoder (frozen — not updated).
            sequences:   List of primer DNA sequences.
            labels:      Binary success labels (N,) ∈ {0.0, 1.0}.
            epochs:      Number of fine-tuning epochs (default 20).
            batch_size:  Mini-batch size for SGD (default 32).

        Returns:
            List[float]: Mean BCE loss per epoch.
        """
        N = len(sequences)
        loss_history = []
        rng = np.random.RandomState(seed=42)

        for epoch in range(epochs):
            indices = rng.permutation(N)
            epoch_losses = []

            for start in range(0, N, batch_size):
                batch_idx = indices[start : start + batch_size]
                batch_loss = 0.0

                # Accumulate gradients over the mini-batch
                acc_grads: Dict[str, np.ndarray] = {
                    "W1": np.zeros_like(self.W1),
                    "b1": np.zeros_like(self.b1),
                    "W2": np.zeros_like(self.W2),
                    "b2": np.zeros_like(self.b2),
                }

                for idx in batch_idx:
                    seq = sequences[int(idx)]
                    y = float(labels[int(idx)])

                    # Forward: extract [CLS] embedding (transformer frozen)
                    cls_emb = transformer.get_cls_embedding(seq)

                    # Forward through classification head (training=True → dropout)
                    p = self.forward(cls_emb, training=True)

                    # BCE loss
                    eps = 1e-8
                    loss = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
                    batch_loss += float(loss)

                    # Backward
                    grads = self.backward(cls_emb, y)
                    for k in acc_grads:
                        acc_grads[k] = acc_grads[k] + grads[k]

                # Average gradients and update
                n_batch = len(batch_idx)
                for k in acc_grads:
                    acc_grads[k] = acc_grads[k] / n_batch

                self.update(acc_grads)
                epoch_losses.append(batch_loss / n_batch)

            mean_loss = float(np.mean(epoch_losses))
            loss_history.append(mean_loss)
            logger.debug(
                f"FineTune Epoch {epoch+1}/{epochs} | Mean BCE = {mean_loss:.4f} "
                f"| Updates: {self._n_updates}"
            )

        logger.info(
            f"FineTuneClassificationHead: fine-tuning complete. "
            f"{epochs} epochs, {self._n_updates} total updates, "
            f"final loss = {loss_history[-1]:.4f}"
        )
        return loss_history

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the classification head weights to a JSON-compatible dict."""
        return {
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "lr": self.lr,
            "clip_norm": self.clip_norm,
            "dropout_rate": self.dropout_rate,
            "n_updates": self._n_updates,
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Loads weights from a serialized dictionary."""
        self.W1 = np.array(data["W1"], dtype=np.float32)
        self.b1 = np.array(data["b1"], dtype=np.float32)
        self.W2 = np.array(data["W2"], dtype=np.float32)
        self.b2 = np.array(data["b2"], dtype=np.float32)
        self.lr = float(data.get("lr", self.lr))
        self.clip_norm = float(data.get("clip_norm", self.clip_norm))
        self.dropout_rate = float(data.get("dropout_rate", self.dropout_rate))
        self._n_updates = int(data.get("n_updates", 0))

        # Reset Adam state to match new weights
        self._mW1 = np.zeros_like(self.W1)
        self._vW1 = np.zeros_like(self.W1)
        self._mb1 = np.zeros_like(self.b1)
        self._vb1 = np.zeros_like(self.b1)
        self._mW2 = np.zeros_like(self.W2)
        self._vW2 = np.zeros_like(self.W2)
        self._mb2 = np.zeros_like(self.b2)
        self._vb2 = np.zeros_like(self.b2)
