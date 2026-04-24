"""MultiQC AI Insights Parser.

Parses MultiQC outputs (JSON/HTML data) to generate human-readable Insights
using the Agent's LLM. Allows the CLI to post-process QC reports and flag
anomalies (like GC-bias, adapter contamination, or poor duplication rates).
"""

from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from .types import LLMProvider, Message, Role

class MultiQCInsightGenerator:
    """Reads multiqc_data.json and uses LLM to generate summary."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def analyze_qc_data(self, multiqc_data_path: str) -> str:
        """Parse raw multiqc JSON data and run through LLM."""
        path = Path(multiqc_data_path)
        if not path.exists():
            return f"Error: MultiQC data not found at {multiqc_data_path}"
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            return f"Failed to parse MultiQC data: {exc}"

        # Extract FastQC general stats (if available) to save context window
        metrics: dict[str, Any] = {}
        if "report_general_stats_data" in data:
            metrics = data["report_general_stats_data"]
            
        # Serialize to small JSON specifically for prompt
        mini_json = json.dumps(metrics, indent=2)
        if len(mini_json) > 4000:
            mini_json = mini_json[:4000] + "\n... (truncated)"

        prompt = (
            "You are a Bioinformatics QC Analyst. Review the following MultiQC metrics "
            "and provide a short, professional summary. Highlight any critical issues "
            "like poor read coverage, high duplication rates, or sequence artifacts.\n\n"
            f"```json\n{mini_json}\n```"
        )
        
        messages = [
            Message(role=Role.SYSTEM, content="Provide concise bioinformatics QC summaries."),
            Message(role=Role.USER, content=prompt)
        ]
        
        response = await self._llm.generate(messages, tools=[])
        return response.content
