"""Centralized configuration via pydantic-settings.

Each subsystem (LLM, Embedding, Reranker, Qdrant) is its own BaseSettings
with an env_prefix, so flat env names like ``LLM_BASE_URL`` map directly to
nested fields. ``.env`` and ``.env.local`` are loaded automatically;
environment variables override file values.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = (".env", ".env.local")


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=_ENV_FILES, extra="ignore")
    base_url: str
    api_key: str
    default_model: str
    reasoning_model: str = "deepseek-r1:671b-64k"
    light_model: str = "deepseek-v4-flash"


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", env_file=_ENV_FILES, extra="ignore")
    base_url: str
    api_key: str
    model: str
    dim: int


class RerankerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RERANKER_", env_file=_ENV_FILES, extra="ignore")
    base_url: str
    api_key: str
    model: str


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", env_file=_ENV_FILES, extra="ignore")
    url: str
    api_key: str = ""
    collection: str = "neblab_abstracts"
    # When set, use qdrant-client's local file-based mode
    # (QdrantClient(path=...)) instead of connecting to url/api_key. Keeps
    # all vectors on-disk locally — no server or cloud cluster required.
    path: str = ""


# Each factory tells pyright the return type explicitly. The `# type: ignore`
# is necessary because BaseSettings populates required fields from env at
# runtime, which pyright cannot see statically.
def _llm_factory() -> "LLMSettings":
    return LLMSettings()  # type: ignore[call-arg]


def _embedding_factory() -> "EmbeddingSettings":
    return EmbeddingSettings()  # type: ignore[call-arg]


def _reranker_factory() -> "RerankerSettings":
    return RerankerSettings()  # type: ignore[call-arg]


def _qdrant_factory() -> "QdrantSettings":
    return QdrantSettings()  # type: ignore[call-arg]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    llm: LLMSettings = Field(default_factory=_llm_factory)
    embedding: EmbeddingSettings = Field(default_factory=_embedding_factory)
    reranker: RerankerSettings = Field(default_factory=_reranker_factory)
    qdrant: QdrantSettings = Field(default_factory=_qdrant_factory)

    postgres_dsn: str = ""
    openalex_email: str = ""
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor (memoized)."""
    return Settings()
