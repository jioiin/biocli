"""Hugging Face Local LLM provider via GPT4All (No server).

Zero HTTP, zero ports, zero telemetry, zero network.
Uses pre-compiled binaries for Windows/Linux/Mac.
"""

import json
import re
from pathlib import Path
from typing import Any

from biopipe.core.types import LLMProvider, Message, Role, ToolCall

class HFLocalLLM:
    """Direct inference using GGUF models from Hugging Face."""

    def __init__(self, model_path: str, n_threads: int = 4):
        from gpt4all import GPT4All
        path = Path(model_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        self._model = GPT4All(model_name=path.name, model_path=str(path.parent), allow_download=False)
        self._model_name = path.stem

    async def generate(self, messages: list[Message], tools: list[dict[str, Any]], stream_callback: Any = None) -> Message:
        # Inject tool schemas into the system prompt
        system_instructions = (
            "You are a bioinformatics assistant. You can use tools to help the user.\n"
            "To use a tool, output a JSON block like this:\n"
            "```json\n"
            '{"tool": "tool_name", "parameters": {"arg1": "val1"}}\n'
            "```\n\n"
            "Available tools:\n"
        )
        for t in tools:
            system_instructions += f"- {t['name']}: {t['description']}. Parameters: {json.dumps(t['parameters'])}\n"

        # Simple chat formatting
        prompt = f"system: {system_instructions}\n"
        for m in messages:
            if m.role == Role.TOOL:
                prompt += f"tool result: {m.content}\n"
            else:
                prompt += f"{m.role.value}: {m.content}\n"
        prompt += "assistant: "

        # Synchronous generate
        response_text = self._model.generate(prompt, max_tokens=1024, temp=0.1)

        if stream_callback:
            stream_callback(response_text)

        # Parse tool calls
        tool_calls = []
        # Find JSON blocks: ```json ... ```
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block)
                if "tool" in data and "parameters" in data:
                    tool_calls.append(ToolCall(
                        tool_name=data["tool"],
                        parameters=data["parameters"],
                        call_id=re.sub(r"\W+", "", data["tool"]) + "_call"
                    ))
            except json.JSONDecodeError:
                continue

        # Remove tool call blocks from final content to avoid showing them to user
        clean_content = re.sub(r"```json\s*.*?\s*```", "", response_text, flags=re.DOTALL).strip()

        return Message(
            role=Role.ASSISTANT,
            content=clean_content or "Calling tool...",
            tool_calls=tool_calls if tool_calls else None
        )

    async def health_check(self) -> bool:
        return True

    def model_id(self) -> str:
        return f"hf:{self._model_name}"
