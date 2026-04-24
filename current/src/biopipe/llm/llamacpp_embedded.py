"""Embedded llama.cpp adapter — direct inference, no server.

Uses llama-cpp-python to run models in-process.
Zero HTTP, zero ports, zero telemetry, zero network.
Requires: pip install llama-cpp-python

This is the recommended backend for maximum privacy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from biopipe.core.errors import LLMConnectionError, LLMTimeoutError
from biopipe.core.types import LLMProvider, Message, Role


class EmbeddedLlamaCpp:
    """Direct llama.cpp inference via Python bindings.

    No server process, no HTTP, no ports.
    Model loaded in-process from GGUF file.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 8192,
        n_threads: int = 4,
        n_gpu_layers: int = -1,  # -1 = auto (all layers to GPU if available)
    ) -> None:
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python is required for embedded mode.\n"
                "Install: pip install llama-cpp-python\n"
                "With CUDA: CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python"
            )

        path = Path(model_path).expanduser()
        if not path.exists():
            raise LLMConnectionError(
                f"Model file not found: {path}\n"
                f"Download with: biopipe setup"
            )

        self._model_path = str(path)
        self._llm = Llama(
            model_path=str(path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        self._model_name = path.stem

    async def generate(
        self, messages: list[Message], tools: list[dict[str, Any]]
    ) -> Message:
        """Generate response from local model.

        Args:
            messages: Conversation history.
            tools: Tool schemas (used for function calling if model supports it).

        Returns:
            Assistant message with generated text.
        """
        formatted = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

        try:
            response = self._llm.create_chat_completion(
                messages=formatted,
                max_tokens=2048,
                temperature=0.1,  # low temp for deterministic code generation
                top_p=0.9,
            )
        except Exception as exc:
            raise LLMTimeoutError(f"Inference failed: {exc}") from exc

        content = response["choices"][0]["message"]["content"]

        return Message(
            role=Role.ASSISTANT,
            content=content or "",
        )

    async def health_check(self) -> bool:
        """Check if model is loaded and responsive."""
        try:
            response = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return bool(response["choices"])
        except Exception:
            return False

    def model_id(self) -> str:
        """Return model filename as ID."""
        return f"local:{self._model_name}"
