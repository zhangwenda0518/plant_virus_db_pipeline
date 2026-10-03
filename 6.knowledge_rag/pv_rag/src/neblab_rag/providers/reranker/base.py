"""RerankerProvider abstract interface."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class RerankResult(BaseModel):
    index: int
    score: float


class RerankerProvider(ABC):
    @abstractmethod
    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]: ...
