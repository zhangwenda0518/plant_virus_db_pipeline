"""Test LLMProvider abstract interface contract."""

import pytest

from neblab_rag.providers.llm.base import (
    ChatMessage,
    ChatRequest,
    LLMProvider,
)


def test_chat_message_roles():
    m = ChatMessage(role="user", content="hi")
    assert m.role == "user"


def test_chat_request_default_temperature():
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.temperature == 0.3


def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]
