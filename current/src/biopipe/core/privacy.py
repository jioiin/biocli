"""Differential Privacy Log Scrubber.

Filters PHI (Protected Health Information), generic patient identifiers, or 
pathogenic metadata before logs are written to the audit trail.
HIPAA compliance utility for BioPipe-CLI.
"""

import re
from typing import NamedTuple


class PrivacyViolation(NamedTuple):
    original: str
    redacted: str
    category: str


class PrivacyScrubber:
    """Scans and redacts PHI from strings."""

    def __init__(self) -> None:
        # Regexes for common PHI and genomic ID patterns
        self._patterns = {
            "EMAIL": re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"),
            "PATIENT_ID": re.compile(r"\b(PT|ID|PAT|patient)[-_: ]?\d{4,9}\b", re.IGNORECASE),
            "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "GENERIC_NAME": re.compile(r"\b(John|Jane)\s+[A-Za-z]+\b"),
            # Prevent leaking exact genomic variant coords if flagged private
            "SENSITIVE_VAR": re.compile(r"\bchr[1-9XTY]{1,2}:\d+-[ATCG]+->[ATCG]+\b")
        }

    def redact(self, text: str) -> str:
        """Replace all matched PHI patterns with [REDACTED]."""
        redacted_text = text
        for category, pattern in self._patterns.items():
            redacted_text = pattern.sub(f"[REDACTED_{category}]", redacted_text)
        return redacted_text
