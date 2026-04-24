"""Tool registry with integrity validation on registration."""

from __future__ import annotations

from typing import Any

from .errors import PermissionDeniedError, ToolNotFoundError, ToolValidationError
from .types import PermissionLevel, Tool


class ToolRegistry:
    """Stores registered tools and generates schemas for LLM function calling."""

    FORBIDDEN_OVERRIDES: set[str] = {
        "__del__", "__getattr__", "__setattr__",
        "__import__", "__subclasses__",
    }

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool after integrity checks."""
        if tool.name in self._tools:
            raise ToolValidationError(f"Duplicate tool name: {tool.name}")

        if tool.required_permission().value > PermissionLevel.GENERATE.value:
            raise PermissionDeniedError(
                f"Tool '{tool.name}' requests {tool.required_permission().name}. "
                f"Max allowed for external tools: GENERATE."
            )

        for attr in self.FORBIDDEN_OVERRIDES:
            if attr in type(tool).__dict__:
                raise ToolValidationError(
                    f"Tool '{tool.name}' overrides forbidden attribute: {attr}"
                )

        schema = tool.parameter_schema
        if not isinstance(schema, dict) or "type" not in schema:
            raise ToolValidationError(
                f"Tool '{tool.name}' has invalid parameter_schema"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Get a tool by name."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return self._tools[name]

    def list_schemas(self) -> list[dict[str, Any]]:
        """Generate JSON schemas for LLM function calling."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameter_schema,
            }
            for t in self._tools.values()
        ]

    def names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
