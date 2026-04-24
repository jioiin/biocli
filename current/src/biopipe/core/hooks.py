"""Deterministic hook system for extending core behavior."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .types import Hook, HookPoint


class HookRegistry:
    """Stores and executes hooks at defined points in the agent loop."""

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[Hook]] = defaultdict(list)

    def register(self, hook: Hook) -> None:
        """Register a hook at its declared point."""
        self._hooks[hook.hook_point()].append(hook)

    async def fire(self, point: HookPoint, context: dict[str, Any]) -> dict[str, Any]:
        """Fire all hooks for a point. Returns modified context.

        If a hook returns None, context passes through unchanged.
        If a hook returns a dict, that becomes the new context.
        """
        current = context
        for hook in self._hooks.get(point, []):
            result = await hook.run(current)
            if result is not None:
                current = result
        return current

    def has_hooks(self, point: HookPoint) -> bool:
        """Check if any hooks are registered for a point."""
        return bool(self._hooks.get(point))
