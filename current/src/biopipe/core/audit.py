"""Audit trail export for compliance.

Exports full session history in two formats:
- JSON (machine-readable, for 21 CFR Part 11 / GxP)
- Markdown (human-readable, for NIH DMS plans)

Every generation is a record: timestamp, model, prompt, output,
safety report, user approval status.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class AuditRecord:
    """Single auditable event."""
    timestamp: str
    event_type: str
    session_id: str
    model_id: str
    user_prompt: str
    generated_output: str
    safety_passed: bool
    safety_violations: list[dict[str, Any]]
    approval_status: str
    script_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditTrail:
    """Collect and export audit records."""

    def __init__(self, session_id: str, model_id: str) -> None:
        self._session_id = session_id
        self._model_id = model_id
        self._records: list[AuditRecord] = []

    def record(
        self,
        event_type: str,
        prompt: str,
        output: str,
        safety_passed: bool,
        violations: list[dict[str, Any]],
        approval: str,
        script_hash: str,
        **extra: Any,
    ) -> None:
        """Add an audit record."""
        self._records.append(AuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            session_id=self._session_id,
            model_id=self._model_id,
            user_prompt=prompt[:500],  # truncate for privacy
            generated_output=output[:2000],
            safety_passed=safety_passed,
            safety_violations=violations,
            approval_status=approval,
            script_hash=script_hash,
            metadata=extra,
        ))

    def export_json(self, path: str | Path) -> Path:
        """Export as JSON (machine-readable)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "audit_version": "1.0",
            "session_id": self._session_id,
            "model_id": self._model_id,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "records": [asdict(r) for r in self._records],
            "total_records": len(self._records),
            "all_passed_safety": all(r.safety_passed for r in self._records),
        }
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def export_markdown(self, path: str | Path) -> Path:
        """Export as Markdown (human-readable, for NIH DMS)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# BioPipe-CLI Audit Trail",
            f"",
            f"**Session:** {self._session_id}",
            f"**Model:** {self._model_id}",
            f"**Exported:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total events:** {len(self._records)}",
            f"",
            f"---",
            f"",
        ]

        for i, rec in enumerate(self._records, 1):
            status = "PASS" if rec.safety_passed else "BLOCKED"
            lines.append(f"## Event {i}: {rec.event_type}")
            lines.append(f"")
            lines.append(f"- **Time:** {rec.timestamp}")
            lines.append(f"- **Safety:** {status}")
            lines.append(f"- **Approval:** {rec.approval_status}")
            lines.append(f"- **Script hash:** `{rec.script_hash[:16]}...`")
            lines.append(f"")
            if rec.safety_violations:
                lines.append(f"**Violations:**")
                for v in rec.safety_violations:
                    lines.append(f"- [{v.get('severity', '?')}] {v.get('description', '?')}")
                lines.append("")
            lines.append(f"---")
            lines.append(f"")

        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def count(self) -> int:
        return len(self._records)
