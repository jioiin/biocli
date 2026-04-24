"""Intent router: maps tool_name from LLM to registered Tool."""

from __future__ import annotations

from .tool_registry import ToolRegistry
from .types import Tool, ToolCall


class Router:
    """Resolve LLM tool_call names to concrete Tool instances."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def resolve(self, tool_call: ToolCall) -> Tool:
        """Look up the tool by name. Raises ToolNotFoundError if missing."""
        return self._registry.get(tool_call.tool_name)
