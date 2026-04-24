"""Beautiful terminal UI components for BioPipe-CLI."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.markdown import Markdown
from typing import Any, Optional

# Global console instance
console = Console()
err_console = Console(stderr=True)

def print_header() -> None:
    """Print the BioPipe CLI header."""
    console.print(Panel.fit("[bold cyan]🧬 BioPipe-CLI[/bold cyan] [grey50]v2.0[/grey50]", border_style="cyan"))

def print_error(msg: str) -> None:
    """Print a rich error message."""
    err_console.print(f"[bold red]ERROR:[/bold red] {msg}")

def print_warning(msg: str) -> None:
    """Print a rich warning message."""
    console.print(f"[bold yellow]WARNING:[/bold yellow] {msg}")

def print_success(msg: str) -> None:
    """Print a rich success message."""
    console.print(f"[bold green]SUCCESS:[/bold green] {msg}")

def print_info(msg: str) -> None:
    """Print an informational message."""
    console.print(f"[bold blue]INFO:[/bold blue] {msg}")

def print_code(code: str, language: str = "bash") -> None:
    """Print syntax highlighted code."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Generated {language.upper()}", border_style="green"))

def render_markdown(text: str) -> None:
    """Render markdown text."""
    md = Markdown(text)
    console.print(md)

def get_spinner(text: str = "Processing...") -> Progress:
    """Return a spinner progress context manager."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )

class StreamingMarkdownPrinter:
    """Helps print streaming markdown token by token smoothly."""
    def __init__(self):
        self.buffer = ""
        self.live = Live(Markdown(""), console=console, refresh_per_second=15, transient=False)
        self.started = False
    
    def append(self, token: str):
        if not self.started:
            self.live.start()
            self.started = True
            
        self.buffer += token
        self.live.update(Markdown(self.buffer))

    def finalize(self):
        if self.started:
            self.live.stop()
        else:
            # If nothing streamed, just print it assuming it failed fast or something
            pass
