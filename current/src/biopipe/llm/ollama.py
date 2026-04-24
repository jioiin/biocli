"""Ollama LLM provider via HTTP API (localhost:11434)."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Callable

from biopipe.core.errors import LLMConnectionError, LLMTimeoutError
from biopipe.core.types import LLMProvider, Message, Role


class OllamaLLM:
    """Ollama API client. Calls POST /api/chat on localhost."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3:8b-instruct-q4_K_M",
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(
        self, 
        messages: list[Message], 
        tools: list[dict[str, Any]], 
        stream_callback: Callable[[str], None] | None = None
    ) -> Message:
        """Send messages to Ollama and return the response.

        Args:
            messages: Conversation history.
            tools: Tool schemas for function calling (Ollama supports this in newer versions).

        Returns:
            Assistant message with the LLM response.

        Raises:
            LLMConnectionError: If Ollama is unreachable.
            LLMTimeoutError: If Ollama doesn't respond in time.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in messages
            ],
            "stream": bool(stream_callback),
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": t,
                }
                for t in tools
            ]

        data = self._post("/api/chat", payload, stream_callback)
        content = data.get("message", {}).get("content", "")

        tool_calls = None
        raw_tool_calls = data.get("message", {}).get("tool_calls")
        if raw_tool_calls:
            from biopipe.core.types import ToolCall
            import uuid
            tool_calls = [
                ToolCall(
                    tool_name=tc["function"]["name"],
                    parameters=tc["function"].get("arguments", {}),
                    call_id=uuid.uuid4().hex[:8],
                )
                for tc in raw_tool_calls
            ]

        return Message(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
        )

    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                return resp.status == 200
        except Exception:
            return False

    def model_id(self) -> str:
        """Return configured model name."""
        return self._model

    def _post(
        self, path: str, payload: dict[str, Any], stream_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Send POST request to Ollama API."""
        url = f"{self._base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # nosec B310
                if payload.get("stream"):
                    full_content = ""
                    final_data = {}
                    for line in resp:
                        if not line.strip():
                            continue
                        chunk = json.loads(line.decode("utf-8"))
                        if "message" in chunk and "content" in chunk["message"]:
                            token = chunk["message"]["content"]
                            full_content += token
                            if stream_callback:
                                stream_callback(token)
                        if chunk.get("done"):
                            final_data = chunk
                    
                    if "message" not in final_data:
                        final_data["message"] = {}
                    final_data["message"]["content"] = full_content
                    return final_data
                else:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMConnectionError(
                f"Cannot reach Ollama at {url}: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"Ollama timed out after {self._timeout}s"
            ) from exc
