"""Plant-virus-specific settings wrapping shared NEBLab configuration.

Reuses LLM, Embedding, Reranker, Postgres config from neblab_rag.config;
adds plant-virus-specific Qdrant collection and OpenAlex email pass-through.
"""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from neblab_rag.config import get_settings as get_neblab_settings, Settings as NeblabSettings

_ENV_FILES = (".env", ".env.local")


class PvQdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PV_QDRANT_", env_file=_ENV_FILES, extra="ignore")
    collection: str = "pv_chunks"


def _pv_qdrant_factory() -> "PvQdrantSettings":
    return PvQdrantSettings()  # type: ignore[call-arg]


class PvSettings(BaseSettings):
    """Plant-virus settings: wraps shared NEBLab settings + pv overrides."""

    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    qdrant: PvQdrantSettings = Field(default_factory=_pv_qdrant_factory)
    openalex_email: str = ""


@lru_cache(maxsize=1)
def get_pv_settings() -> PvSettings:
    return PvSettings()


# Convenience: build a composite that has both domain settings
class CompositeSettings:
    """Combines NEBLab shared infra settings with PV domain settings."""

    def __init__(self):
        self._neblab = get_neblab_settings()
        self._pv = get_pv_settings()

    @property
    def llm(self):
        return self._neblab.llm

    @property
    def embedding(self):
        return self._neblab.embedding

    @property
    def reranker(self):
        return self._neblab.reranker

    @property
    def postgres_dsn(self) -> str:
        return self._neblab.postgres_dsn

    @property
    def qdrant_url(self) -> str:
        return self._neblab.qdrant.url

    @property
    def qdrant_api_key(self) -> str:
        return self._neblab.qdrant.api_key

    @property
    def qdrant_collection(self) -> str:
        return self._pv.qdrant.collection

    @property
    def embedding_dim(self) -> int:
        return self._neblab.embedding.dim

    @property
    def openalex_email(self) -> str:
        return self._pv.openalex_email or self._neblab.openalex_email

    @property
    def log_level(self) -> str:
        return self._neblab.log_level


@lru_cache(maxsize=1)
def get_composite_settings() -> CompositeSettings:
    return CompositeSettings()
