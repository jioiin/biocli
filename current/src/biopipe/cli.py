"""BioPipe-CLI: local AI agent for bioinformatics pipeline generation.

Entry points:
    biopipe              → Interactive REPL (default, like Claude Code)
    biopipe -p "..."     → One-shot query (like claude -p "...")
    biopipe setup        → Download and configure local LLM
    biopipe health       → Check system health
    biopipe plugins ...  → Manage plugins
    biopipe feedback ... → Submit RLHF feedback
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

try:
    import typer
except ImportError:
    print("Typer is required. Install: pip install typer", file=sys.stderr)
    sys.exit(1)

from biopipe.core.config import Config
from biopipe.core.errors import BioPipeError, LLMConnectionError, SafetyBlockedError
from biopipe.core.runtime import AgentRuntime
from biopipe.core.ui import (
    console, print_header, print_error, print_success, print_info,
    StreamingMarkdownPrinter,
)

app = typer.Typer(
    name="biopipe",
    help="Local AI agent for bioinformatics pipeline generation.",
    add_completion=False,
    invoke_without_command=True,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_llm(config: Config):
    """Create LLM provider based on config."""
    from biopipe.llm.ollama import OllamaLLM
    return OllamaLLM(
        base_url=config.ollama_url,
        model=config.model,
        timeout=config.llm_timeout,
    )


def _build_runtime(config: Config) -> AgentRuntime:
    """Build the runtime. Plugins provide tools — core has none built-in."""
    llm = _get_llm(config)

    rag = None
    try:
        from biopipe.rag.retriever import RAGRetriever
        rag_instance = RAGRetriever(db_path=str(config.rag_db_path))
        if not rag_instance.is_empty():
            rag = rag_instance
    except Exception:
        pass

    try:
        from biopipe.llm.prompts import SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE
    except ImportError:
        SYSTEM_PROMPT = ""
        RAG_CONTEXT_TEMPLATE = "{chunks}"

    runtime = AgentRuntime(config, llm, system_prompt=SYSTEM_PROMPT, rag=rag, rag_template=RAG_CONTEXT_TEMPLATE)
    runtime.load_plugins()
    return runtime


# ── Default: REPL ────────────────────────────────────────────────────────────

@app.callback()
def main_callback(
    ctx: typer.Context,
    prompt: str = typer.Option(None, "--prompt", "-p", help="One-shot prompt (non-interactive)"),
    model: str = typer.Option(None, "--model", "-m", help="Override LLM model"),
) -> None:
    """BioPipe-CLI — local AI agent for bioinformatics.

    Run without arguments to start the interactive REPL.
    Use -p for one-shot queries.
    """
    # Set model override before loading config
    if model:
        os.environ["BIOPIPE_MODEL"] = model

    # If a subcommand is being invoked, skip REPL
    if ctx.invoked_subcommand is not None:
        return

    # One-shot mode: biopipe -p "QC pipeline for FASTQ files"
    if prompt:
        _run_oneshot(prompt)
        return

    # Default: Interactive REPL
    _run_repl()


def _run_repl() -> None:
    """Launch the interactive REPL (default mode)."""
    from biopipe.repl import BioPipeREPL
    config = Config.load()
    repl = BioPipeREPL(config)
    repl.start()


def _run_oneshot(prompt: str) -> None:
    """Run a single prompt and exit (like claude -p)."""
    config = Config.load()
    runtime = _build_runtime(config)

    printer = StreamingMarkdownPrinter()
    console.print()

    try:
        result = asyncio.run(runtime.run(prompt, stream_callback=printer.append))
    except LLMConnectionError:
        printer.finalize()
        print_error("Cannot reach Ollama. Is it running?")
        print_info(f"Expected at: {config.ollama_url}")
        print_info("Start with: ollama serve")
        raise typer.Exit(1)
    except SafetyBlockedError as exc:
        printer.finalize()
        print_error(f"SAFETY BLOCKED: {exc}")
        raise typer.Exit(2)
    except BioPipeError as exc:
        printer.finalize()
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        printer.finalize()
        asyncio.run(runtime.shutdown())

    console.print()


# ── Subcommands ──────────────────────────────────────────────────────────────

@app.command()
def setup(
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Enable offline setup (no downloads). Requires --model-path.",
    ),
    model_path: str | None = typer.Option(
        None,
        "--model-path",
        help="Path to a pre-downloaded local .gguf model file.",
    ),
) -> None:
    """Download and configure a local LLM model for BioPipe-CLI."""
    from biopipe.setup_wizard import run_setup
    if offline:
        print_info("Running setup in offline mode.")
        if not model_path:
            print_error("Offline mode requires --model-path.")
            raise typer.Exit(1)
    elif model_path:
        print_info("--model-path was provided without --offline and will be ignored.")

    run_setup(offline=offline, model_path=model_path)


@app.command()
def health() -> None:
    """Check system health (Ollama, RAM, plugins, RAG)."""
    from biopipe.core.ui import print_doctor_results
    import psutil

    config = Config.load()
    checks: dict[str, bool] = {}

    # Ollama
    try:
        import urllib.request
        req = urllib.request.Request(f"{config.ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            checks["Ollama server"] = resp.status == 200
    except Exception:
        checks["Ollama server"] = False

    # RAM
    ram_gb = psutil.virtual_memory().total / (1024**3)
    checks[f"RAM ({ram_gb:.0f} GB)"] = ram_gb >= 8

    # Python
    checks[f"Python {sys.version_info.major}.{sys.version_info.minor}"] = sys.version_info >= (3, 11)

    # WASM
    try:
        import wasmtime  # noqa: F401
        checks["WASM sandbox"] = True
    except ImportError:
        checks["WASM sandbox"] = False

    # RAG
    try:
        import chromadb  # noqa: F401
        checks["RAG engine"] = True
    except ImportError:
        checks["RAG engine"] = False

    print_doctor_results(checks)

    if not all(checks.values()):
        raise typer.Exit(1)


@app.command()
def index(
    tools: list[str] = typer.Argument(..., help="Tool names to index (e.g., samtools bwa)"),
) -> None:
    """Index bioinformatics tool documentation for RAG."""
    try:
        from biopipe.rag.indexer import RAGIndexer
    except ImportError:
        print_error("ChromaDB required. Install: pip install 'biopipe-cli[rag]'")
        raise typer.Exit(1)

    config = Config.load()
    indexer = RAGIndexer(db_path=str(config.rag_db_path))

    for tool_name in tools:
        count = indexer.index_manpage(tool_name)
        if count == 0:
            count = indexer.index_help(tool_name)
        if count > 0:
            print_success(f"Indexed {tool_name}: {count} chunks")
        else:
            print_info(f"Skipped {tool_name}: no man page or --help found")

    stats = indexer.stats()
    print_info(f"Total chunks in index: {stats['total_chunks']}")


@app.command("index-security")
def index_security() -> None:
    """Download and index Security docs (OWASP) into RAG."""
    import urllib.request
    import tempfile
    try:
        from biopipe.rag.indexer import RAGIndexer
    except ImportError:
        print_error("ChromaDB required. Install: pip install 'biopipe-cli[rag]'")
        raise typer.Exit(1)

    urls = {
        "OWASP_Secure_Coding": "https://raw.githubusercontent.com/OWASP/secure-coding-practices-quick-reference-guide/master/README.md",
    }

    config = Config.load()
    indexer = RAGIndexer(db_path=str(config.rag_db_path))

    with tempfile.TemporaryDirectory() as tmpdir:
        for name, url in urls.items():
            print_info(f"Downloading {name}...")
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8")

                path = os.path.join(tmpdir, f"{name}.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

                count = indexer.index_file(path, tool_name=name.lower())
                print_success(f"Indexed {name}: {count} chunks")
            except Exception as exc:
                print_error(f"Failed to index {name}: {exc}")

    stats = indexer.stats()
    print_info(f"Total chunks in index: {stats['total_chunks']}")


@app.command("explain")
def explain(
    file_path: str = typer.Argument(..., help="Path to pipeline script"),
) -> None:
    """Analyze and explain a bioinformatics pipeline script."""
    path = Path(file_path)
    if not path.exists():
        print_error(f"File not found: {file_path}")
        raise typer.Exit(1)

    code_content = path.read_text(encoding="utf-8")
    prompt = (
        f"Explain this bioinformatics script ({path.name}) step by step. "
        f"What tools does it use? What inputs/outputs?\n\n"
        f"```{path.suffix}\n{code_content}\n```"
    )

    config = Config.load()
    runtime = _build_runtime(config)
    printer = StreamingMarkdownPrinter()
    console.print()

    try:
        asyncio.run(runtime.run(prompt, stream_callback=printer.append))
    except Exception as exc:
        printer.finalize()
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        printer.finalize()
        asyncio.run(runtime.shutdown())

    console.print()


@app.command("debug")
def debug(
    log_path: str = typer.Argument(..., help="Path to error log"),
    lines: int = typer.Option(200, help="Number of tail lines to read"),
) -> None:
    """Read a crash log and suggest fixes."""
    path = Path(log_path)
    if not path.exists():
        print_error(f"Log not found: {log_path}")
        raise typer.Exit(1)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content_lines = f.readlines()
    tail = "".join(content_lines[-lines:])

    prompt = (
        f"My bioinformatics pipeline crashed. Identify the root cause from these "
        f"last {lines} lines of {path.name} and provide a fix:\n\n```log\n{tail}\n```"
    )

    config = Config.load()
    runtime = _build_runtime(config)
    printer = StreamingMarkdownPrinter()
    console.print()

    try:
        asyncio.run(runtime.run(prompt, stream_callback=printer.append))
    except Exception as exc:
        printer.finalize()
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        printer.finalize()
        asyncio.run(runtime.shutdown())

    console.print()


@app.command()
def feedback(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Original request prompt"),
    rating: int = typer.Option(..., "--rating", "-r", help="Rating from 1 to 5"),
    text: str = typer.Argument(..., help="Feedback text"),
) -> None:
    """Submit RLHF feedback for fine-tuning."""
    from biopipe.core.rlhf import RLHFDataStore

    if rating < 1 or rating > 5:
        print_error("Rating must be between 1 and 5")
        raise typer.Exit(1)

    store = RLHFDataStore()
    store.log_feedback(prompt=prompt, script="", rating=rating, feedback_text=text)
    print_success("Feedback stored in local RLHF dataset.")


@app.command("plugins")
def plugins_cmd(
    action: str = typer.Argument("list", help="Action: list, info, validate, install"),
    name: str = typer.Argument("", help="Plugin name, path, or git URL"),
) -> None:
    """Manage plugins: list, info, validate, install."""
    from biopipe.core.plugin_sdk import PluginLoader

    plugin_dir = str(Path.home() / ".biopipe" / "plugins")
    loader = PluginLoader(plugin_dir=plugin_dir)

    if action == "list":
        manifests = loader.discover()
        if not manifests:
            print_info(f"No plugins found in {plugin_dir}")
            return
        console.print()
        for m in manifests:
            console.print(f"  [bold]●[/bold] {m.name} [dim]v{m.version}[/dim] — {m.description}")
        console.print()

    elif action == "info" and name:
        manifests = loader.discover()
        found = [m for m in manifests if m.name == name]
        if not found:
            print_error(f"Plugin '{name}' not found.")
            raise typer.Exit(1)
        m = found[0]
        from rich.table import Table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim")
        table.add_column(style="bold white")
        table.add_row("Name", m.name)
        table.add_row("Version", m.version)
        table.add_row("Author", m.author)
        table.add_row("Description", m.description)
        table.add_row("Entry point", m.entry_point or "(WASM)")
        table.add_row("Tools", ", ".join(m.tools) or "(none)")
        table.add_row("Permissions", ", ".join(m.permissions) or "(none)")
        console.print()
        console.print(table)
        console.print()

    elif action == "validate" and name:
        import json
        from biopipe.core.plugin_sdk import PluginManifest
        from biopipe.core.errors import PermissionDeniedError, ToolValidationError

        manifest_path = Path(name) / "manifest.json"
        if not manifest_path.exists():
            print_error(f"No manifest.json found in {name}")
            raise typer.Exit(1)

        try:
            data = json.loads(manifest_path.read_text())
            manifest = PluginManifest(**{
                k: data.get(k, v.default if hasattr(v, 'default') else "")
                for k, v in PluginManifest.__dataclass_fields__.items()
            })
            loader._validate_manifest(manifest)
            print_success("Manifest: OK")

            if manifest.entry_point or manifest.wasm_file:
                result = loader.load_plugin(manifest)
                print_success(f"Plugin loaded: {len(result['tools'])} tools")

            print_success(f"Plugin '{manifest.name}' is valid.")
        except (PermissionDeniedError, ToolValidationError) as exc:
            print_error(str(exc))
            raise typer.Exit(1)

    elif action == "install" and name:
        import subprocess
        plugin_url = name
        plugin_name = plugin_url.rstrip("/").split("/")[-1]
        if plugin_name.endswith(".git"):
            plugin_name = plugin_name[:-4]

        target_dir = Path(plugin_dir) / plugin_name
        if target_dir.exists():
            print_error(f"Plugin directory already exists: {target_dir}")
            raise typer.Exit(1)

        print_info(f"Cloning {plugin_url}...")
        Path(plugin_dir).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", plugin_url, str(target_dir)],
                capture_output=True, text=True, check=True
            )
            print_success(f"Installed plugin '{plugin_name}'.")
        except subprocess.CalledProcessError as exc:
            print_error(f"Failed: {exc.stderr}")
            raise typer.Exit(1)
        except FileNotFoundError:
            print_error("Git is not installed.")
            raise typer.Exit(1)

    else:
        print_info("Usage: biopipe plugins [list|info <name>|validate <path>|install <git_url>]")


def main() -> None:
    """Entry point for pip install console_scripts."""
    app()


if __name__ == "__main__":
    main()
