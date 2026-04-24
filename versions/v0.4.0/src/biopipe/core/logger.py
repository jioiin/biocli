"""Structured JSON logger for audit trail and reproducibility."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """JSON logger. Every step is logged with timestamp and session_id."""

    REDACT_KEYS: set[str] = {"api_key", "token", "secret", "password", "credential"}
    MAX_CONTENT_LEN: int = 10240

    def __init__(self, session_id: str | None = None, log_file: str | None = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self._file = open(log_file, "a") if log_file else None  # noqa: SIM115

    def log(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Emit a structured log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event": event_type,
            "data": self._sanitize(data or {}),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()
        else:
            print(line, file=sys.stderr)

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact secrets and truncate large values."""
        clean: dict[str, Any] = {}
        for key, val in data.items():
            if any(r in key.lower() for r in self.REDACT_KEYS):
                clean[key] = "[REDACTED]"
            elif isinstance(val, str) and len(val) > self.MAX_CONTENT_LEN:
                clean[key] = val[: self.MAX_CONTENT_LEN] + f"... [truncated, {len(val)} total]"
            elif isinstance(val, dict):
                clean[key] = self._sanitize(val)
            else:
                clean[key] = val
        return clean

    def close(self) -> None:
        """Flush and close log file."""
        if self._file:
            self._file.close()
