"""Re-exports neblab_rag.db.engine for plant_virus_rag modules.

PV-specific functions are thin wrappers that keep the plant virus domain
separate at the API level while sharing the underlying engine/session pool.
"""

from neblab_rag.db.engine import get_engine as _get_engine
from neblab_rag.db.engine import get_session as get_pv_session

__all__ = ["get_pv_session"]
