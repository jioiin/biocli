"""BioPipe-CLI Ultimate UI: Powered by PulseEngine & LayoutManager."""

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from .theme import get_theme
from .pulse_engine import PulseEngine, PulseState
from .dashboard_renderer import DashboardRenderer, SystemVitals
from .layout_manager import LayoutManager

console = Console()
theme = get_theme()

class BioPipeUI:
    def __init__(self, model_name: str = "Local Model"):
        self.engine = PulseEngine()
        self.dashboard = DashboardRenderer(console)
        self.layout = LayoutManager(console)
        self.vitals = SystemVitals(model_name=model_name, ram_total_mb=8192.0) # Placeholder
        self.live = None

    def start(self):
        self.layout.update_header("🧬 BioPipe-CLI v2.5 | 100% Local")
        self.layout.update_footer("Ctrl+C: Exit | Ctrl+H: Help")
        self.layout.update_sidebar(self.dashboard.render_vitals(self.vitals))
        self.layout.update_main(Panel("Ready. Waiting for input...", title="Activity", border_style="green"))

        self.live = Live(self.layout.layout, console=console, refresh_per_second=4)
        self.live.start()

    def stop(self):
        if self.live:
            self.live.stop()

    def update_vitals(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.vitals, k):
                setattr(self.vitals, k, v)
        self.layout.update_sidebar(self.dashboard.render_vitals(self.vitals))

    def update_main(self, content: str, title: str = "Activity"):
        self.layout.update_main(Panel(Markdown(content), title=title, border_style="blue"))

# Global UI instance (optional, for simple CLI usage)
_ui_instance = None

def get_ui(model_name: str = "Local") -> BioPipeUI:
    global _ui_instance
    if _ui_instance is None:
        _ui_instance = BioPipeUI(model_name)
    return _ui_instance

# Backward compatibility helpers
def print_header() -> None:
    get_ui().layout.update_header("🧬 BioPipe-CLI v2.5 | 100% Local")

def print_error(msg: str) -> None:
    console.print(f"[bold red]ERROR:[/bold red] {msg}")

def print_success(msg: str) -> None:
    console.print(f"[bold green]SUCCESS:[/bold green] {msg}")

def print_info(msg: str) -> None:
    console.print(f"[bold blue]INFO:[/bold blue] {msg}")

def render_markdown(text: str) -> None:
    console.print(Markdown(text))

def get_spinner(text: str = "Processing..."):
    from rich.progress import Progress, SpinnerColumn, TextColumn
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )

class StreamingMarkdownPrinter:
    def __init__(self):
        self.buffer = ""
    def append(self, token: str):
        self.buffer += token
        # Simple print for now to avoid Live conflicts in non-TUI mode
        console.print(token, end="")
    def finalize(self):
        console.print("\n")
