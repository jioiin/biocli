"""BioPipe-CLI Core type contracts.

Every interface lives here. The core depends ONLY on these types,
never on concrete implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable, Callable


class PermissionLevel(Enum):
    """Permission tiers. MVP caps at GENERATE (dry-run only)."""
    READ_ONLY = auto()
    GENERATE = auto()
    WRITE_WORKSPACE = auto()
    EXECUTE = auto()


@dataclass(frozen=True)
class ToolCall:
    """Immutable request from LLM to execute a tool."""
    tool_name: str
    parameters: dict[str, Any]
    call_id: str


@dataclass
class ToolResult:
    """Result of a tool execution."""
    call_id: str
    success: bool
    output: str
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)


class Role(Enum):
    """Message role in the conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """Single message in the agent loop conversation."""
    role: Role
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_result: ToolResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Interface for any LLM backend."""
    async def generate(
        self, 
        messages: list[Message], 
        tools: list[dict[str, Any]], 
        stream_callback: Callable[[str], None] | None = None
    ) -> Message: ...
    async def health_check(self) -> bool: ...
    def model_id(self) -> str: ...


@runtime_checkable
class Tool(Protocol):
    """Interface for pluggable tools."""
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameter_schema(self) -> dict[str, Any]: ...
    def required_permission(self) -> PermissionLevel: ...
    async def execute(self, params: dict[str, Any]) -> ToolResult: ...
    def validate_params(self, params: dict[str, Any]) -> list[str]: ...


class HookPoint(Enum):
    """Deterministic hook points in the agent loop."""
    BEFORE_LLM_CALL = auto()
    AFTER_LLM_CALL = auto()
    BEFORE_TOOL_EXECUTE = auto()
    AFTER_TOOL_EXECUTE = auto()
    BEFORE_SCRIPT_OUTPUT = auto()
    ON_ERROR = auto()


@runtime_checkable
class Hook(Protocol):
    """Pre/post hooks. Return None to continue, dict to modify context."""
    def hook_point(self) -> HookPoint: ...
    async def run(self, context: dict[str, Any]) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class SafetyViolation:
    """Single safety issue found in generated code."""
    severity: str
    line: int | None
    description: str
    pattern: str


@dataclass
class SafetyReport:
    """Aggregate safety validation result."""
    passed: bool
    violations: list[SafetyViolation]
    script_hash: str


@dataclass(frozen=True)
class SandboxedInput:
    """Immutable container for sanitized user input."""
    raw_user_input: str
    sanitized: str
    injection_score: float
