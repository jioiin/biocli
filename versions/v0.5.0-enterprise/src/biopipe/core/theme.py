# src/biopipe/core/theme.py
from dataclasses import dataclass, field
from typing import Final
from rich.style import Style
from rich.text import Text

@dataclass(frozen=True)
class LabColors:
    """Centralized color theme for BioPipe CLI."""
    primary: Final[str] = "#00D9FF"
    secondary: Final[str] = "#7B61FF"
    accent: Final[str] = "#00FF88"
    success: Final[str] = "#00FF88"
    warning: Final[str] = "#FFB800"
    error: Final[str] = "#FF4757"
    info: Final[str] = "#54A0FF"
    gather: Final[str] = "#54A0FF"
    action: Final[str] = "#FF9F43"
    verify: Final[str] = "#A55EEA"
    audit: Final[str] = "#2ED573"
    muted: Final[str] = "#636E72"
    border: Final[str] = "#2D3436"
    background: Final[str] = "#1E1E2E"
    heading: Final[str] = "#FFFFFF"
    body: Final[str] = "#DFE6E9"
    subtle: Final[str] = "#B2BEC3"

    @classmethod
    def dark(cls) -> "LabColors":
        return cls()

    def style(self, name: str, bold: bool = False) -> Style:
        color = getattr(self, name, self.body)
        base = Style(color=color)
        return base + Style(bold=True) if bold else base

    def status_indicator(self, state: str) -> Text:
        color_map = {
            "idle": self.muted,
            "gathering": self.gather,
            "actioning": self.action,
            "verifying": self.verify,
            "auditing": self.audit,
            "complete": self.success,
            "error": self.error,
        }
        color = color_map.get(state.lower(), self.muted)
        return Text("●", style=Style(color=color, bold=True))

_current_theme: LabColors = LabColors.dark()

def get_theme() -> LabColors:
    return _current_theme
