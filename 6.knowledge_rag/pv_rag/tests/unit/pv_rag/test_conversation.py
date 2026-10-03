"""Unit tests for conversation model and multi-turn support."""

from plant_virus_rag.rag.conversation import (
    ConvMessage,
    conversation_summary,
    latest_user_message,
)


def test_latest_user_message_returns_last_user_turn() -> None:
    msgs = [
        ConvMessage(role="user", content="First question"),
        ConvMessage(role="assistant", content="Answer"),
        ConvMessage(role="user", content="Second question"),
    ]
    assert latest_user_message(msgs) == "Second question"


def test_latest_user_message_empty_on_no_user() -> None:
    msgs = [ConvMessage(role="assistant", content="Hello")]
    assert latest_user_message(msgs) == ""


def test_latest_user_message_skips_empty_content() -> None:
    msgs = [
        ConvMessage(role="user", content="  "),  # trimmed to empty
        ConvMessage(role="user", content="Valid query"),
    ]
    assert latest_user_message(msgs) == "Valid query"


def test_conversation_summary_respects_max_chars() -> None:
    msgs = [
        ConvMessage(role="user", content="What is TMV?"),
        ConvMessage(role="assistant", content="Tobacco mosaic virus is a..."),
        ConvMessage(role="user", content="Tell me more about its transmission"),
    ]
    summary = conversation_summary(msgs, max_chars=50)
    assert len(summary) <= 60  # ~max_chars + overhead


def test_conversation_summary_includes_latest_turns() -> None:
    msgs = [
        ConvMessage(role="user", content="Q1"),
        ConvMessage(role="assistant", content="A1"),
        ConvMessage(role="user", content="Q2"),
    ]
    summary = conversation_summary(msgs)
    assert "Q2" in summary


def test_convmessage_trims_whitespace() -> None:
    msg = ConvMessage(role="user", content="  hello  ")
    assert msg.content == "hello"
