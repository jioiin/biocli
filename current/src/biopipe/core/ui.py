"""Beautiful terminal UI components for BioPipe-CLI.

Design philosophy: match the polish of Claude Code / Gemini CLI.
Rich panels, streaming markdown, inline tool calls, permission prompts.
"""

import sys
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule

# ── Global Consoles ──────────────────────────────────────────────────────────

console = Console()
err_console = Console(stderr=True)

# ── Colors ───────────────────────────────────────────────────────────────────

ACCENT = "cyan"
ACCENT_BOLD = "bold cyan"
SUCCESS = "bold green"
ERROR = "bold red"
WARNING = "bold yellow"
DIM = "dim"
MUTED = "grey50"


# ── Banner ───────────────────────────────────────────────────────────────────

def print_banner(version: str, model: str, rag_status: str, plugins: list[str],
                 wasm_ready: bool = False) -> None:
    """Print the startup banner — Claude Code / Gemini CLI style."""
    
    # Title line
    title = Text()
    title.append("🧬 BioPipe-CLI", style=ACCENT_BOLD)
    title.append(f"  v{version}", style=MUTED)

    # Status items
    model_text = Text()
    model_text.append("  Model   ", style=DIM)
    model_text.append(model, style="bold white")

    rag_text = Text()
    rag_text.append("  RAG     ", style=DIM)
    if rag_status == "ready":
        rag_text.append("● ready", style=SUCCESS)
    else:
        rag_text.append("○ " + rag_status, style=MUTED)

    plugin_text = Text()
    plugin_text.append("  Plugins ", style=DIM)
    if plugins:
        plugin_text.append(f"{len(plugins)} loaded", style="bold white")
        plugin_text.append(f" ({', '.join(plugins)})", style=MUTED)
    else:
        plugin_text.append("none", style=MUTED)

    wasm_text = Text()
    wasm_text.append("  WASM    ", style=DIM)
    if wasm_ready:
        wasm_text.append("● sandbox active", style=SUCCESS)
    else:
        wasm_text.append("○ not loaded", style=MUTED)

    # Combine
    body = Text()
    body.append_text(model_text)
    body.append("\n")
    body.append_text(rag_text)
    body.append("\n")
    body.append_text(plugin_text)
    body.append("\n")
    body.append_text(wasm_text)

    panel = Panel(
        body,
        title=title,
        title_align="left",
        border_style=ACCENT,
        padding=(0, 1),
        subtitle="[dim]Type a request or /help for commands[/dim]",
        subtitle_align="right",
    )
    console.print(panel)
    console.print()


def print_welcome_tip() -> None:
    """Print a quick tip below the banner."""
    console.print(
        f"  [{MUTED}]Tip: Place a BIOPIPE.md in your project root to configure default behavior.[/{MUTED}]"
    )
    console.print()


# ── Messages ─────────────────────────────────────────────────────────────────

def print_error(msg: str) -> None:
    err_console.print(f"  [{ERROR}]✗[/{ERROR}] {msg}")

def print_warning(msg: str) -> None:
    console.print(f"  [{WARNING}]⚠[/{WARNING}] {msg}")

def print_success(msg: str) -> None:
    console.print(f"  [{SUCCESS}]✓[/{SUCCESS}] {msg}")

def print_info(msg: str) -> None:
    console.print(f"  [{ACCENT}]ℹ[/{ACCENT}] {msg}")

def print_header() -> None:
    """Legacy — kept for backwards compat."""
    console.print(Panel.fit("[bold cyan]🧬 BioPipe-CLI[/bold cyan]", border_style="cyan"))


# ── Tool Calls (inline, like Claude Code) ────────────────────────────────────

def print_tool_call(tool_name: str, status: str = "running") -> None:
    """Show inline tool call status."""
    if status == "running":
        console.print(f"  [dim]⚙[/dim]  [bold]{tool_name}[/bold] [dim]…[/dim]")
    elif status == "done":
        console.print(f"  [{SUCCESS}]✓[/{SUCCESS}]  [bold]{tool_name}[/bold] [dim]done[/dim]")
    elif status == "error":
        console.print(f"  [{ERROR}]✗[/{ERROR}]  [bold]{tool_name}[/bold] [dim]failed[/dim]")


def print_permission_request(action: str, detail: str = "") -> bool:
    """Inline permission request — returns True if user allows."""
    console.print()
    console.print(f"  [{WARNING}]⚠ Permission required[/{WARNING}]")
    console.print(f"    Action: [bold]{action}[/bold]")
    if detail:
        console.print(f"    Detail: [dim]{detail}[/dim]")

    try:
        response = console.input(f"    [{ACCENT}]Allow? (y/N):[/{ACCENT}] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# ── Session Stats ────────────────────────────────────────────────────────────

def print_session_stats(tokens_in: int, tokens_out: int, elapsed: float,
                        iterations: int) -> None:
    """Print session statistics at /cost or exit."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=DIM)
    table.add_column(style="bold white")
    table.add_row("Input tokens", f"{tokens_in:,}")
    table.add_row("Output tokens", f"{tokens_out:,}")
    table.add_row("Iterations", str(iterations))
    table.add_row("Elapsed", f"{elapsed:.1f}s")
    
    panel = Panel(table, title="[dim]Session Stats[/dim]", border_style=DIM, expand=False)
    console.print(panel)


# ── Doctor ───────────────────────────────────────────────────────────────────

def print_doctor_results(checks: dict[str, bool]) -> None:
    """Print health check results — styled like /doctor."""
    console.print()
    for component, ok in checks.items():
        icon = f"[{SUCCESS}]✓[/{SUCCESS}]" if ok else f"[{ERROR}]✗[/{ERROR}]"
        console.print(f"  {icon}  {component}")
    console.print()

    if all(checks.values()):
        print_success("All systems operational.")
    else:
        failed = [k for k, v in checks.items() if not v]
        print_error(f"Issues detected: {', '.join(failed)}")


# ── Slash Command Help ───────────────────────────────────────────────────────

SLASH_COMMANDS_HELP = """
[bold cyan]Session[/bold cyan]
  /compact         Compress conversation history
  /clear           Clear terminal
  /reset           Reset pipeline state
  /cost            Show token usage & timing

[bold cyan]Pipeline[/bold cyan]
  /plan            Show current pipeline plan
  /save [file]     Save generated script
  /execute         Execute script (requires permission)

[bold cyan]System[/bold cyan]
  /doctor          Diagnose system (Ollama, RAM, GPU)
  /model [name]    Switch LLM model
  /config          Show current configuration
  /plugins         List loaded plugins

[bold cyan]Other[/bold cyan]
  /help            Show this help
  /quit            Exit BioPipe-CLI
"""

def print_slash_help() -> None:
    """Print slash command reference."""
    console.print(Panel(
        SLASH_COMMANDS_HELP.strip(),
        title="[bold]Commands[/bold]",
        border_style=ACCENT,
        expand=False,
        padding=(0, 1),
    ))


# ── Code Display ─────────────────────────────────────────────────────────────

def print_code(code: str, language: str = "bash") -> None:
    """Print syntax-highlighted code in a panel."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"[dim]{language.upper()}[/dim]", border_style="green"))


def render_markdown(text: str) -> None:
    """Render markdown text."""
    console.print(Markdown(text))


def get_spinner(text: str = "Processing...") -> Progress:
    """Return a spinner progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )


# ── Streaming ────────────────────────────────────────────────────────────────

class StreamingMarkdownPrinter:
    """Real-time streaming markdown renderer with thinking indicator."""

    def __init__(self) -> None:
        self.buffer = ""
        self.live = Live(
            Text("  ○ Thinking…", style=DIM),
            console=console,
            refresh_per_second=12,
            transient=False,
        )
        self.started = False
        self._first_token = True

    def append(self, token: str) -> None:
        if not self.started:
            self.live.start()
            self.started = True

        if self._first_token:
            self._first_token = False
            # Clear "Thinking..." on first real token

        self.buffer += token
        self.live.update(Markdown(self.buffer))

    def finalize(self) -> None:
        if self.started:
            self.live.stop()
