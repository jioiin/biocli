"""Session manager: conversation history, compaction, sandbox integration."""

from __future__ import annotations

import json
from typing import Any

from .sandbox import InputSandbox
from .types import Message, Role, SandboxedInput


class SessionManager:
    """Manages the message array — the only state of the agent loop."""

    def __init__(self, system_prompt: str, max_tokens: int = 8192) -> None:
        self._messages: list[Message] = [
            Message(role=Role.SYSTEM, content=system_prompt)
        ]
        self._max_tokens = max_tokens
        self._sandbox = InputSandbox()

    def add(self, message: Message) -> None:
        """Add a message to history."""
        self._messages.append(message)

    def add_user_message(self, user_input: str) -> SandboxedInput:
        """Sanitize user input through sandbox, then add to history."""
        sandboxed = self._sandbox.wrap(user_input)
        formatted = self._sandbox.format_for_llm(sandboxed)
        self.add(Message(role=Role.USER, content=formatted))
        return sandboxed

    def messages(self) -> list[Message]:
        """Return full message history."""
        return list(self._messages)

    def token_count(self) -> int:
        """Approximate token count (4 chars ≈ 1 token)."""
        return sum(len(m.content) // 4 for m in self._messages)

    def compact(self) -> None:
        """Compress old messages when approaching token limit.

        Keeps: system prompt + last 3 user/assistant pairs.
        Summarizes everything else into one system message.
        """
        if self.token_count() < int(self._max_tokens * 0.75):
            return

        system = self._messages[0]
        recent = self._messages[1:][-6:]  # last 3 pairs

        middle = self._messages[1:-6]
        if not middle:
            return

        summary_parts = []
        for msg in middle:
            summary_parts.append(f"[{msg.role.value}]: {msg.content[:200]}")
        summary_text = "Previous conversation summary:\n" + "\n".join(summary_parts)

        self._messages = [
            system,
            Message(role=Role.SYSTEM, content=summary_text),
            *recent,
        ]

    def export(self) -> dict[str, Any]:
        """Serialize session for persistence."""
        return {
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "metadata": m.metadata,
                }
                for m in self._messages
            ],
            "max_tokens": self._max_tokens,
        }

    @classmethod
    def restore(cls, data: dict[str, Any]) -> SessionManager:
        """Deserialize a saved session with security validation.

        Security: only the FIRST message can be SYSTEM role.
        Additional SYSTEM messages in the JSON are SKIPPED
        to prevent session injection attacks (vector V10).
        """
        if not data.get("messages"):
            raise ValueError("Session data has no messages")

        first = data["messages"][0]
        if first.get("role") != "system":
            raise ValueError("First message must be system prompt")

        system_prompt = first["content"]
        session = cls(system_prompt, data.get("max_tokens", 8192))

        for msg_data in data["messages"][1:]:
            role = Role(msg_data["role"])
            # SECURITY: block injected SYSTEM messages
            if role == Role.SYSTEM:
                continue  # silently skip — don't load attacker's instructions
            session.add(Message(
                role=role,
                content=msg_data["content"],
                metadata=msg_data.get("metadata", {}),
            ))
        return session
