"""BioPipe-CLI Interactive REPL — Claude Code / Gemini CLI style.

This is the primary user interface. Users type `biopipe` and land here.
Maintains session state, supports slash commands, streams markdown,
and loads BIOPIPE.md project context.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PTStyle

from biopipe.core.config import Config
from biopipe.core.deliberation import DeliberationEngine
from biopipe.core.errors import BioPipeError, LLMConnectionError, SafetyBlockedError
from biopipe.core.execution import ExecutionEngine
from biopipe.core.pipeline_state import PipelineState
from biopipe.core.plugin_sdk import PluginLoader
from biopipe.core.runtime import AgentRuntime
from biopipe.core.ui import (
    console, print_banner, print_welcome_tip, print_error, print_success,
    print_info, print_warning, print_slash_help, print_doctor_results,
    print_session_stats, print_code, print_tool_call, print_permission_request,
    StreamingMarkdownPrinter, render_markdown, ACCENT, MUTED,
)

VERSION = "0.5.0"

# Slash command autocomplete
_SLASH_COMMANDS = [
    "/help", "/compact", "/clear", "/reset", "/cost",
    "/plan", "/save", "/execute",
    "/doctor", "/model", "/config", "/plugins",
    "/quit", "/exit", "/q",
]

_PROMPT_STYLE = PTStyle.from_dict({
    "prompt": "#00bcd4 bold",  # cyan
})


class BioPipeREPL:
    """Interactive REPL — the primary interface for BioPipe-CLI."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._pipeline = PipelineState()
        self._runtime: AgentRuntime | None = None
        self._execution: ExecutionEngine | None = None
        self._deliberation: DeliberationEngine | None = None
        self._plugin_loader = PluginLoader(
            plugin_dir=str(Path.home() / ".biopipe" / "plugins")
        )

        # Session metrics
        self._session_start = time.time()
        self._total_iterations = 0

        # Prompt toolkit session with history + autocomplete
        history_path = Path.home() / ".biopipe" / "history.txt"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self._prompt_session = PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(_SLASH_COMMANDS, sentence=True),
            style=_PROMPT_STYLE,
        )

    def start(self) -> None:
        """Start the interactive REPL."""
        self._init_runtime()
        self._load_biopipe_md()
        self._print_banner()

        while True:
            try:
                user_input = self._prompt_session.prompt(
                    [("class:prompt", "❯ ")],
                ).strip()
            except (EOFError, KeyboardInterrupt):
                self._exit()
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_prompt(user_input)

    # ── Initialization ───────────────────────────────────────────────────

    def _init_runtime(self) -> None:
        """Initialize runtime with LLM, tools, and plugins."""
        from biopipe.llm.ollama import OllamaLLM

        llm = OllamaLLM(
            base_url=self._config.ollama_url,
            model=self._config.model,
            timeout=self._config.llm_timeout,
        )

        rag = None
        try:
            from biopipe.rag.retriever import RAGRetriever
            rag_instance = RAGRetriever(db_path=str(self._config.rag_db_path))
            if not rag_instance.is_empty():
                rag = rag_instance
        except Exception:
            pass

        try:
            from biopipe.llm.prompts import SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE
        except ImportError:
            SYSTEM_PROMPT = ""
            RAG_CONTEXT_TEMPLATE = "{chunks}"

        self._runtime = AgentRuntime(
            self._config, llm,
            system_prompt=SYSTEM_PROMPT, rag=rag, rag_template=RAG_CONTEXT_TEMPLATE,
        )
        self._runtime.load_plugins()

        # Deliberation engine
        tool_names = self._runtime._registry.names()
        self._deliberation = DeliberationEngine(tool_names)

        # Execution engine
        self._execution = ExecutionEngine(
            permission_level=self._config.permission_level,
            safety=self._runtime._safety,
            logger=self._runtime._logger,
            workspace=self._config.output_dir,
        )

    def _load_biopipe_md(self) -> None:
        """Load BIOPIPE.md from current directory (like CLAUDE.md)."""
        biopipe_md = Path.cwd() / "BIOPIPE.md"
        if biopipe_md.exists():
            try:
                content = biopipe_md.read_text(encoding="utf-8")
                if content.strip():
                    print_info(f"Loaded project context from BIOPIPE.md")
                    # Inject into system prompt via session
                    from biopipe.core.types import Message, Role
                    self._runtime._session.add(Message(
                        role=Role.SYSTEM,
                        content=f"Project context from BIOPIPE.md:\n{content}"
                    ))
            except Exception:
                pass

    def _print_banner(self) -> None:
        """Print the startup banner."""
        # RAG status
        rag_status = "not indexed"
        try:
            from biopipe.rag.retriever import RAGRetriever
            rag = RAGRetriever(db_path=str(self._config.rag_db_path))
            if not rag.is_empty():
                rag_status = "ready"
        except Exception:
            rag_status = "unavailable"

        # Plugins
        plugins = self._plugin_loader.list_loaded()

        # WASM
        wasm_ready = False
        try:
            import wasmtime  # noqa: F401
            wasm_ready = True
        except ImportError:
            pass

        print_banner(
            version=VERSION,
            model=self._config.model,
            rag_status=rag_status,
            plugins=plugins,
            wasm_ready=wasm_ready,
        )
        print_welcome_tip()

    # ── Slash Commands ───────────────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """Route slash commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: print_slash_help(),
            "/compact": lambda: self._cmd_compact(),
            "/clear": lambda: console.clear(),
            "/reset": lambda: self._cmd_reset(),
            "/cost": lambda: self._cmd_cost(),
            "/plan": lambda: self._cmd_plan(),
            "/save": lambda: self._cmd_save(arg),
            "/execute": lambda: self._cmd_execute(),
            "/doctor": lambda: self._cmd_doctor(),
            "/model": lambda: self._cmd_model(arg),
            "/config": lambda: self._cmd_config(),
            "/plugins": lambda: self._cmd_plugins(),
            "/quit": lambda: self._exit(),
            "/exit": lambda: self._exit(),
            "/q": lambda: self._exit(),
        }

        handler = handlers.get(command)
        if handler:
            handler()
        else:
            print_error(f"Unknown command: {command}. Type /help")

    def _cmd_compact(self) -> None:
        """Compress session history."""
        self._runtime._session.compact()
        msgs = list(self._runtime._session.messages())
        print_success(f"Session compacted to {len(msgs)} messages.")

    def _cmd_reset(self) -> None:
        self._pipeline = PipelineState()
        print_success("Pipeline state reset.")

    def _cmd_cost(self) -> None:
        elapsed = time.time() - self._session_start
        print_session_stats(
            tokens_in=0,  # Would need LLM to track these
            tokens_out=0,
            elapsed=elapsed,
            iterations=self._total_iterations,
        )

    def _cmd_plan(self) -> None:
        if self._pipeline.is_empty():
            print_info("No pipeline built yet. Start with a request.")
            return
        console.print()
        print_code(self._pipeline.format_for_llm(), "yaml")

    def _cmd_save(self, filename: str) -> None:
        if not self._pipeline.current_script:
            print_info("No script to save.")
            return
        fname = filename or "pipeline.sh"
        path = self._execution.save_script(self._pipeline.current_script, fname)
        print_success(f"Saved to {path}")

    def _cmd_execute(self) -> None:
        if not self._pipeline.current_script:
            print_info("No script to execute.")
            return

        if not self._execution.can_execute():
            print_warning("Execution disabled (dry-run mode).")
            print_info("To enable: export BIOPIPE_PERMISSION_LEVEL=EXECUTE")
            path = self._execution.save_script(
                self._pipeline.current_script, "pipeline.sh"
            )
            print_success(f"Script saved instead: {path}")
            return

        # Show script
        console.print()
        print_code(self._pipeline.current_script, "bash")

        # Permission request
        allowed = print_permission_request(
            "Execute generated script",
            detail=f"{len(self._pipeline.current_script)} bytes"
        )
        if not allowed:
            print_info("Execution cancelled.")
            return

        from biopipe.core.deliberation import ActionPlan, ProposedAction
        plan = ActionPlan(
            task_summary="User-requested execution",
            actions=[ProposedAction(
                tool_name="bash",
                action_description="Execute generated pipeline",
                justification="User explicitly requested execution",
                alternatives_considered=[],
            )],
            tools_available=self._runtime._registry.names(),
            tools_selected=["bash"],
            tools_rejected=[],
            overall_justification="User confirmed execution",
            estimated_output="Pipeline results in output directory",
        )
        self._deliberation.approve(plan)

        try:
            result = self._execution.execute(
                self._pipeline.current_script,
                plan=plan,
                user_confirmed=True,
            )
            if result.success:
                print_success(f"Completed (exit code: {result.exit_code})")
                if result.stdout:
                    console.print(result.stdout[:2000])
            else:
                print_error(f"Failed (exit code: {result.exit_code})")
                if result.stderr:
                    console.print(result.stderr[:2000])
        except (SafetyBlockedError, BioPipeError) as exc:
            print_error(str(exc))

    def _cmd_doctor(self) -> None:
        """Run system diagnostics."""
        import shutil
        import psutil

        checks: dict[str, bool] = {}

        # Ollama
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._config.ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                checks["Ollama server"] = resp.status == 200
        except Exception:
            checks["Ollama server"] = False

        # RAM
        ram_gb = psutil.virtual_memory().total / (1024**3)
        checks[f"RAM ({ram_gb:.0f} GB)"] = ram_gb >= 8

        # Python
        checks[f"Python {sys.version_info.major}.{sys.version_info.minor}"] = sys.version_info >= (3, 11)

        # WASM Runtime
        try:
            import wasmtime  # noqa: F401
            checks["WASM sandbox (wasmtime)"] = True
        except ImportError:
            checks["WASM sandbox (wasmtime)"] = False

        # RAG
        try:
            import chromadb  # noqa: F401
            checks["RAG engine (chromadb)"] = True
        except ImportError:
            checks["RAG engine (chromadb)"] = False

        print_doctor_results(checks)

    def _cmd_model(self, name: str) -> None:
        if not name:
            print_info(f"Current model: {self._config.model}")
            print_info("Usage: /model <name>  (e.g., /model qwen2.5-coder:7b)")
            return
        # Hot-swap would require reinitializing LLM — for now just inform
        print_info(f"Model switching requires restart. Set env:")
        console.print(f"  [dim]export BIOPIPE_MODEL={name}[/dim]")

    def _cmd_config(self) -> None:
        from rich.table import Table
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Setting", style="dim")
        table.add_column("Value", style="bold white")
        table.add_row("model", self._config.model)
        table.add_row("ollama_url", self._config.ollama_url)
        table.add_row("output_dir", self._config.output_dir)
        table.add_row("permission", self._config.permission_level.name)
        table.add_row("max_iterations", str(getattr(self._config, 'max_iterations', 10)))
        console.print()
        console.print(table)
        console.print()

    def _cmd_plugins(self) -> None:
        loaded = self._plugin_loader.list_loaded()
        if not loaded:
            print_info("No plugins loaded.")
            print_info("Plugin directory: ~/.biopipe/plugins/")
            return
        console.print()
        for name in loaded:
            console.print(f"  [bold]●[/bold] {name}")
        console.print()

    # ── Prompt Handling ──────────────────────────────────────────────────

    def _handle_prompt(self, user_input: str) -> None:
        """Handle natural language prompt with streaming output."""
        # Inject pipeline state
        if not self._pipeline.is_empty():
            augmented = (
                f"{self._pipeline.format_for_llm()}\n\n"
                f"User request: {user_input}"
            )
        else:
            augmented = user_input

        printer = StreamingMarkdownPrinter()
        console.print()

        try:
            result = asyncio.run(
                self._runtime.run(augmented, stream_callback=printer.append)
            )
            self._total_iterations += 1
        except LLMConnectionError:
            printer.finalize()
            print_error("Cannot reach Ollama. Is it running?")
            print_info(f"Expected at: {self._config.ollama_url}")
            print_info("Start with: ollama serve")
            return
        except SafetyBlockedError as exc:
            printer.finalize()
            print_error(f"SAFETY BLOCKED: {exc}")
            return
        except BioPipeError as exc:
            printer.finalize()
            print_error(str(exc))
            return
        except Exception as exc:
            printer.finalize()
            print_error(f"Unexpected error: {exc}")
            return

        printer.finalize()
        console.print()

        # Extract script from response
        if result and ("#!/" in result or "set -euo pipefail" in result):
            self._pipeline.update_script(result)
            print_info("Script captured. Use /plan to view, /save to save.")

    # ── Exit ─────────────────────────────────────────────────────────────

    def _exit(self) -> None:
        """Clean exit with stats."""
        elapsed = time.time() - self._session_start
        console.print()
        if self._total_iterations > 0:
            print_session_stats(0, 0, elapsed, self._total_iterations)
        console.print(f"  [{MUTED}]Goodbye.[/{MUTED}]")
        console.print()
        if self._runtime:
            asyncio.run(self._runtime.shutdown())
        sys.exit(0)
