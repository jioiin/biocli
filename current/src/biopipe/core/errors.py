"""BioPipe-CLI error hierarchy.

All exceptions inherit from BioPipeError for unified catching.
"""


class BioPipeError(Exception):
    """Base exception for all BioPipe-CLI errors."""


class ConfigError(BioPipeError):
    """Configuration loading or validation failure."""


class LLMConnectionError(BioPipeError):
    """Cannot reach the LLM backend (Ollama)."""


class LLMTimeoutError(BioPipeError):
    """LLM did not respond within the timeout."""


class ToolNotFoundError(BioPipeError):
    """Requested tool is not registered."""


class ToolValidationError(BioPipeError):
    """Tool parameters or structure are invalid."""


class ToolExecutionError(BioPipeError):
    """Tool execution failed."""


class PermissionDeniedError(BioPipeError):
    """Permission level insufficient for the requested operation."""


class SafetyBlockedError(BioPipeError):
    """Generated code blocked by safety validator."""


class SessionOverflowError(BioPipeError):
    """Session exceeded maximum token count."""


class CompactionError(BioPipeError):
    """Session compaction failed."""


class InjectionDetectedError(BioPipeError):
    """Prompt injection attempt detected."""
