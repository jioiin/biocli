"""Tool scheduler: sequential execution with timeout and validation."""

from __future__ import annotations

import asyncio

from .errors import ToolExecutionError, ToolValidationError
from .permissions import PermissionPolicy
from .tool_registry import ToolRegistry
from .types import ToolCall, ToolResult


class ToolScheduler:
    """Execute tool calls sequentially with permission checks and timeout."""

    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionPolicy,
        timeout: int = 30,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._timeout = timeout

    async def schedule(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Execute calls sequentially. Each is validated and permission-checked."""
        results: list[ToolResult] = []
        for call in calls:
            result = await self._execute_one(call)
            results.append(result)
        return results

    async def _execute_one(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call with full checks."""
        tool = self._registry.get(call.tool_name)

        self._permissions.check(tool, call)

        errors = tool.validate_params(call.parameters)
        if errors:
            raise ToolValidationError(
                f"Invalid params for '{call.tool_name}': {'; '.join(errors)}"
            )

        try:
            result = await asyncio.wait_for(
                tool.execute(call.parameters),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ToolExecutionError(
                f"Tool '{call.tool_name}' timed out after {self._timeout}s"
            ) from None
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool '{call.tool_name}' failed: {exc}"
            ) from exc

        return result
