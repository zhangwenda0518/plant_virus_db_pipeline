"""Load plant virus eval question sets.

Reuses neblab_rag.eval.data for loading and EvalCase/EvalSet models.
"""

from pathlib import Path

from neblab_rag.eval.data import EvalCase, EvalSet, load_eval_set

__all__ = ["EvalCase", "EvalSet", "load_eval_set"]
