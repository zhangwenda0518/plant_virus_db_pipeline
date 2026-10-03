"""LLMProvider abstract interface and request/response data models."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # None = use provider default
    temperature: float = 0.3
    max_tokens: int = 2048
    stop: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    content: str
    model: str
    finish_reason: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class StreamChunk(BaseModel):
    delta: str
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract LLM provider. Implementations wrap a specific vendor API."""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    @abstractmethod
    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chunks. Implementations are async generators (use ``yield``)."""
        if False:  # pragma: no cover - abstract async-gen marker
            yield StreamChunk(delta="")
