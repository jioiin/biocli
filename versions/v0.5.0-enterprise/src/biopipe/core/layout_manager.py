# src/biopipe/core/layout_manager.py
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from typing import Optional

class LayoutManager:
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="sidebar", ratio=1),
            Layout(name="main", ratio=3),
        )

    def update_header(self, title: str):
        self.layout["header"].update(Panel(Text(title, justify="center", style="bold cyan"), border_style="cyan"))

    def update_sidebar(self, renderable: RenderableType):
        self.layout["sidebar"].update(renderable)

    def update_main(self, renderable: RenderableType):
        self.layout["main"].update(renderable)

    def update_footer(self, text: str):
        self.layout["footer"].update(Panel(Text(text, style="dim"), border_style="dim"))
