"""OpenAI-compatible LLM provider for BioPipe-CLI.

Can connect to vLLM, DeepSeek Coder, LMStudio, or text-generation-webui locally.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from biopipe.core.errors import LLMConnectionError, LLMTimeoutError
from biopipe.core.types import LLMProvider, Message, Role

try:
    from openai import AsyncOpenAI
    import openai
except ImportError:
    pass

class OpenAICompatibleLLM:
    """Wrapper around openai wrapper to talk to generic local backends (vLLM, etc.)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model: str = "local-model",
        api_key: str = "NOT_NEEDED_FOR_LOCAL",
        timeout: int = 60,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("Package 'openai' is required. Run: pip install openai")

        self._model = model
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    async def generate(
        self, 
        messages: list[Message], 
        tools: list[dict[str, Any]], 
        stream_callback: Callable[[str], None] | None = None
    ) -> Message:
        """Send messages to the OpenAI-compatible endpoint."""
        
        oai_messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "stream": bool(stream_callback),
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": t,
                }
                for t in tools
            ]

        try:
            response = await self._client.chat.completions.create(**kwargs)
            
            if kwargs["stream"]:
                full_content = ""
                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        token = delta.content
                        full_content += token
                        if stream_callback:
                            stream_callback(token)
                            
                return Message(
                    role=Role.ASSISTANT,
                    content=full_content,
                    tool_calls=None # Tool calling during streaming is complex, MVP assumes content
                )
            else:
                choice = response.choices[0]
                content = choice.message.content or ""
                
                tool_calls = None
                if choice.message.tool_calls:
                    from biopipe.core.types import ToolCall
                    import uuid
                    tool_calls = [
                        ToolCall(
                            tool_name=tc.function.name,
                            parameters=json.loads(tc.function.arguments),
                            call_id=tc.id or uuid.uuid4().hex[:8],
                        )
                        for tc in choice.message.tool_calls
                    ]

                return Message(
                    role=Role.ASSISTANT,
                    content=content,
                    tool_calls=tool_calls,
                )

        except openai.APIConnectionError as exc:
            raise LLMConnectionError(f"Cannot reach local OpenAI-compatible endpoint: {exc}")
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError("Local OpenAI-compatible endpoint timed out.")

    async def health_check(self) -> bool:
        """Check if server is running."""
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    def model_id(self) -> str:
        return self._model
