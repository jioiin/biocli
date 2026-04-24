"""Input sandbox: delimiter wrapping and injection detection."""

from __future__ import annotations

import re

from .types import SandboxedInput

_INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(previous|above|all)\s+instructions",
    r"you\s+are\s+now\s+",
    r"forget\s+(everything|your|all)",
    r"system\s*prompt",
    r"act\s+as\s+(root|admin|sudo)",
    r"override\s+(safety|security|rules)",
    r"disregard\s+(safety|rules|instructions)",
    r"new\s+instructions?\s*:",
    r"<\/?system>",
    r"\[INST\]",
    r"<<SYS>>",
    r"<\|im_start\|>",
]

_STRIP_TAGS: list[str] = [
    "<s>", "</s>", "[INST]", "[/INST]",
    "<<SYS>>", "<</SYS>>", "<|im_start|>", "<|im_end|>",
]


class InputSandbox:
    """Wrap user input with delimiters and score injection risk."""

    OPEN_TAG = "<user_request>"
    CLOSE_TAG = "</user_request>"

    def wrap(self, user_input: str) -> SandboxedInput:
        """Sanitize and wrap user input."""
        sanitized = self._strip_tags(user_input)
        score = self._score_risk(sanitized)
        return SandboxedInput(
            raw_user_input=user_input,
            sanitized=sanitized,
            injection_score=score,
        )

    def format_for_llm(self, sandboxed: SandboxedInput) -> str:
        """Format for LLM context with delimiters."""
        return f"{self.OPEN_TAG}\n{sandboxed.sanitized}\n{self.CLOSE_TAG}"

    def _strip_tags(self, text: str) -> str:
        """Remove delimiter injection attempts and LLM instruction tags."""
        result = text.replace(self.OPEN_TAG, "").replace(self.CLOSE_TAG, "")
        for tag in _STRIP_TAGS:
            result = result.replace(tag, "")
        return result

    def _score_risk(self, text: str) -> float:
        """Heuristic risk score: 0.0 (safe) to 1.0 (likely injection)."""
        hits = sum(
            1 for p in _INJECTION_PATTERNS
            if re.search(p, text, re.IGNORECASE)
        )
        return min(hits / 3.0, 1.0)
