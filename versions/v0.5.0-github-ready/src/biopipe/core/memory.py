"""Context memory: persistent memory across sessions.

Stores facts learned about the user's environment, preferences,
and past pipelines. JSON file on local disk. Never sent anywhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """Single fact remembered across sessions."""
    key: str
    value: str
    source: str        # "user", "auto", "system"
    timestamp: str
    category: str      # "genome", "tool_preference", "cluster", "project", "history"


class ContextMemory:
    """Persistent local memory. Reads/writes ~/.biopipe/memory.json."""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or Path.home() / ".biopipe" / "memory.json")
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def remember(self, key: str, value: str, category: str = "project",
                 source: str = "auto") -> None:
        """Store a fact."""
        self._entries[key] = MemoryEntry(
            key=key, value=value, source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
        )
        self._save()

    def recall(self, key: str) -> str | None:
        """Recall a fact by key."""
        entry = self._entries.get(key)
        return entry.value if entry else None

    def recall_category(self, category: str) -> list[MemoryEntry]:
        """Recall all facts in a category."""
        return [e for e in self._entries.values() if e.category == category]

    def forget(self, key: str) -> bool:
        """Remove a fact."""
        if key in self._entries:
            del self._entries[key]
            self._save()
            return True
        return False

    def format_for_llm(self) -> str:
        """Format relevant memories for LLM context."""
        if not self._entries:
            return ""

        parts = ["<memory>"]
        by_category: dict[str, list[MemoryEntry]] = {}
        for entry in self._entries.values():
            by_category.setdefault(entry.category, []).append(entry)

        for cat, entries in sorted(by_category.items()):
            parts.append(f"  [{cat}]")
            for e in entries:
                parts.append(f"    {e.key}: {e.value}")

        parts.append("</memory>")
        return "\n".join(parts)

    def all_entries(self) -> list[MemoryEntry]:
        """List all entries."""
        return list(self._entries.values())

    def _load(self) -> None:
        """Load from disk."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data:
                entry = MemoryEntry(**item)
                self._entries[entry.key] = entry
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        """Save to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "key": e.key, "value": e.value, "source": e.source,
                "timestamp": e.timestamp, "category": e.category,
            }
            for e in self._entries.values()
        ]
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
