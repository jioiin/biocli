"""RLHF Data Collector.

Collects user feedback on generated pipelines to build a local dataset
for Reinforcement Learning from Human Feedback (RLHF) or DPO fine-tuning.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone


class RLHFDataStore:
    """Manages appending user preferences to a local JSONL dataset."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = Path.home() / ".biopipe" / "rlhf_dataset.jsonl"
        else:
            self._db_path = Path(db_path)
            
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def log_feedback(self, prompt: str, script: str, rating: int, feedback_text: str) -> None:
        """Log a preference pair. Rating is 1 (bad) to 5 (good)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "completion": script,
            "reward": rating,
            "user_feedback": feedback_text
        }
        
        with open(self._db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
