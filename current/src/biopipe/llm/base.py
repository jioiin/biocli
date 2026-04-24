"""LLM provider base and mock implementation for testing."""

from __future__ import annotations

from biopipe.core.types import LLMProvider, Message, Role


class MockLLM:
    """Mock LLM for testing. Returns canned responses."""

    def __init__(self, response: str = "Mock response") -> None:
        self._response = response
        self._model = "mock-llm-v1"

    async def generate(self, messages: list[Message], tools: list[dict], **kwargs) -> Message:
        """Return a canned response."""
        return Message(role=Role.ASSISTANT, content=self._response)

    async def health_check(self) -> bool:
        """Always healthy."""
        return True

    def model_id(self) -> str:
        """Return mock model ID."""
        return self._model
