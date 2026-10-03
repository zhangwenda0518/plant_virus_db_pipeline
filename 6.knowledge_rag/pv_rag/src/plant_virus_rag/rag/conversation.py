"""Conversation domain model — ported from neblab_rag Sprint 5e.

A request is now a list of messages instead of a single query string.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Role = Literal["user", "assistant"]


class ConvMessage(BaseModel):
    role: Role
    content: str

    @field_validator("content")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()


def latest_user_message(messages: list[ConvMessage]) -> str:
    """Return the most recent user-authored content."""
    for m in reversed(messages):
        if m.role == "user" and m.content:
            return m.content
    return ""


def conversation_summary(messages: list[ConvMessage], *, max_chars: int = 1200) -> str:
    """Render the conversation as a compact transcript for prompts."""
    lines: list[str] = []
    used = 0
    for m in reversed(messages):
        line = f"{m.role.upper()}: {m.content}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines))
