"""Test DeepSeekProvider with mocked HTTP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.llm.base import ChatMessage, ChatRequest
from neblab_rag.providers.llm.deepseek import DeepSeekProvider


@pytest.fixture
def provider() -> DeepSeekProvider:
    return DeepSeekProvider(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        default_model="deepseek-v3.2",
    )


@pytest.mark.asyncio
async def test_chat_calls_correct_endpoint(provider: DeepSeekProvider):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "x",
        "model": "deepseek-v3.2",
        "choices": [
            {
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as mock_post:
        resp = await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))

    assert resp.content == "hi"
    assert resp.model == "deepseek-v3.2"
    assert resp.prompt_tokens == 5
    assert mock_post.call_args.kwargs["url"] == "https://api.example.com/v1/chat/completions"
