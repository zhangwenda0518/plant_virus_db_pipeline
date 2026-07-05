"""PrimerForge: A Hybrid Thermodynamic and Machine Learning Platform for Pangenome-Aware PCR Primer Design.

Exposes the primary biophysical engine, machine learning scorer, pangenome specificity checks,
and integer linear programming optimizer.
"""

__version__ = "0.1.0"
__author__ = "PrimerForge Contributors"

from primerforge.biophysics import BiophysicsEngine, PrimerPair, PrimerSequence
try:
    from primerforge.specificity import SpecificityEngine, AlignmentHit, VariantAwareFilter
except ImportError:
    SpecificityEngine = None
    AlignmentHit = None
    VariantAwareFilter = None

try:
    from primerforge.ml_scorer import MLScorer
except ImportError:
    MLScorer = None

try:
    from primerforge.optimizer import MultiplexOptimizer, TiledAmpliconRouter
except ImportError:
    MultiplexOptimizer = None
    TiledAmpliconRouter = None

try:
    from primerforge.data_curation import DataCurationPipeline
except ImportError:
    DataCurationPipeline = None

__all__ = [
    "BiophysicsEngine",
    "PrimerPair",
    "PrimerSequence",
    "SpecificityEngine",
    "AlignmentHit",
    "VariantAwareFilter",
    "MLScorer",
    "MultiplexOptimizer",
    "TiledAmpliconRouter",
    "DataCurationPipeline",
]
