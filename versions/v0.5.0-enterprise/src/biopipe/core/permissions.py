"""Permission policy with hard cap at GENERATE for external tools."""

from __future__ import annotations

from .errors import PermissionDeniedError
from .types import PermissionLevel, Tool, ToolCall


class PermissionPolicy:
    """Zero-trust permission model. system_level is read-only after init."""

    __slots__ = ("_system_level",)  # prevent adding new attributes

    def __init__(self, level: PermissionLevel = PermissionLevel.GENERATE) -> None:
        object.__setattr__(self, "_system_level", level)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(
            f"PermissionPolicy is immutable. Cannot set '{name}'. "
            f"This is a security invariant."
        )

    @property
    def system_level(self) -> PermissionLevel:
        return self._system_level

    def check(self, tool: Tool, call: ToolCall) -> None:
        """Raise PermissionDeniedError if tool exceeds allowed level."""
        required = tool.required_permission()

        if required.value > PermissionLevel.GENERATE.value:
            raise PermissionDeniedError(
                f"Tool '{tool.name}' requested {required.name}, "
                f"but maximum allowed is GENERATE. "
                f"This is a security policy, not a bug."
            )

        if self._system_level.value < required.value:
            raise PermissionDeniedError(
                f"Current level {self._system_level.name} < "
                f"required {required.name} for tool '{tool.name}'"
            )
