# src/biopipe/core/dashboard_renderer.py
from dataclasses import dataclass
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

@dataclass
class SystemVitals:
    model_name: str = "Unknown"
    context_window: int = 0
    tokens_used: int = 0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    rag_health_score: float = 0.0
    rag_documents_loaded: int = 0
    errors_last_hour: int = 0

class DashboardRenderer:
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def _format_ram_bar(self, used: float, total: float) -> Text:
        if total <= 0: return Text("N/A", style="dim")
        pct = min((used / total) * 100, 100)
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        color = "green" if pct < 70 else "yellow" if pct < 90 else "red"
        return Text(f"[{bar}] {pct:.1f}%", style=color)

    def render_vitals(self, vitals: SystemVitals) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_row("[cyan]Model:[/]", vitals.model_name)
        table.add_row("[cyan]RAM:[/]", self._format_ram_bar(vitals.ram_used_mb, vitals.ram_total_mb))

        status = "HEALTHY" if vitals.rag_health_score > 0.8 else "DEGRADED"
        color = "green" if status == "HEALTHY" else "yellow"
        table.add_row("[cyan]RAG:[/]", f"[{color}]{status}[/]")
        table.add_row("[cyan]Docs:[/]", str(vitals.rag_documents_loaded))

        return Panel(table, title="[bold]System[/]", border_style="blue")
