"""BioPipe-CLI: local AI agent for bioinformatics pipeline generation.

Usage:
    biopipe "сделай QC для paired-end FASTQ"
    biopipe --model llama3:8b "RNA-seq pipeline for mouse"
    biopipe index samtools bwa fastqc
    biopipe health
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
from biopipe.core.ui import console, print_header, print_error, print_success, print_info, get_spinner, render_markdown

app = typer.Typer(
    name="biopipe",
    help="Local AI agent for bioinformatics pipeline generation.",
    add_completion=False,
)


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
    # Tools come from plugins in ~/.biopipe/plugins/
    # Install: git clone <plugin-repo> ~/.biopipe/plugins/<name>
    runtime.load_plugins()
    return runtime


@app.command()
def generate(
    prompt: str = typer.Argument(..., help="Natural language pipeline request"),
    model: str = typer.Option(None, "--model", "-m", help="Model name"),
    output_dir: str = typer.Option(None, "--output-dir", "-o", help="Output directory"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Generate and validate plan only (no script generation)"),
    require_plan_approval: bool = typer.Option(False, "--require-plan-approval", help="Stop after validated plan for manual approval"),
) -> None:
    """Generate a bioinformatics pipeline script from natural language."""
    # Config is frozen — set env vars before loading
    if model:
        os.environ["BIOPIPE_MODEL"] = model
    if output_dir:
        os.environ["BIOPIPE_OUTPUT_DIR"] = output_dir

    config = Config.load()
    runtime = _build_runtime(config)

    try:
        from biopipe.core.ui import StreamingMarkdownPrinter
        printer = StreamingMarkdownPrinter()
        
        print_header()
        print_info("Agent reasoning and streaming response...")
        
        try:
            result = asyncio.run(
                runtime.run(
                    prompt,
                    stream_callback=printer.append,
                    plan_only=plan_only,
                    require_plan_approval=require_plan_approval,
                )
            )
        except Exception as exc:
            printer.finalize()
            raise exc

        printer.finalize()
        print_success("Agent finished execution:")
    except LLMConnectionError:
        print_error("Cannot reach Ollama. Is it running?")
        print_info(f"Expected at: {config.ollama_url}")
        print_info("Start with: ollama serve")
        raise typer.Exit(1)
    except SafetyBlockedError as exc:
        print_error(f"SAFETY BLOCKED: {exc}")
        raise typer.Exit(2)
    except BioPipeError as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        asyncio.run(runtime.shutdown())


@app.command()
def index(
    tools: list[str] = typer.Argument(..., help="Tool names to index (e.g., samtools bwa)"),
) -> None:
    """Index bioinformatics tool documentation for RAG."""
    try:
        from biopipe.rag.indexer import RAGIndexer
    except ImportError:
        typer.echo("ChromaDB required. Install: pip install chromadb", err=True)
        raise typer.Exit(1)

    config = Config.load()
    indexer = RAGIndexer(db_path=str(config.rag_db_path))

    for tool_name in tools:
        count = indexer.index_manpage(tool_name)
        if count == 0:
            count = indexer.index_help(tool_name)
        if count > 0:
            typer.echo(f"  Indexed {tool_name}: {count} chunks")
        else:
            typer.echo(f"  Skipped {tool_name}: no man page or --help found")

    stats = indexer.stats()
    typer.echo(f"\nTotal chunks in index: {stats['total_chunks']}")


@app.command("index-security")
def index_security() -> None:
    """Download and index Security docs (OWASP, Arcanum-Sec) into RAG from Github."""
    import urllib.request
    import tempfile
    import os
    try:
        from biopipe.rag.indexer import RAGIndexer
    except ImportError:
        typer.echo("ChromaDB required. Install: pip install chromadb", err=True)
        raise typer.Exit(1)

    urls = {
        "OWASP_Secure_Coding": "https://raw.githubusercontent.com/OWASP/secure-coding-practices-quick-reference-guide/master/README.md",
        "AI_Anti_Patterns": "https://raw.githubusercontent.com/Arcanum-Sec/sec-context/main/README.md"
    }

    config = Config.load()
    indexer = RAGIndexer(db_path=str(config.rag_db_path))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for name, url in urls.items():
            typer.echo(f"Downloading {name}...")
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                    content = resp.read().decode("utf-8")
                
                path = os.path.join(tmpdir, f"{name}.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                count = indexer.index_file(path, tool_name=name.lower())
                typer.echo(f"  Indexed {name}: {count} chunks")
            except Exception as exc:
                typer.echo(f"  Failed to index {name}: {exc}", err=True)

    stats = indexer.stats()
    typer.echo(f"\nTotal chunks in index: {stats['total_chunks']}")


@app.command("explain")
def explain(
    file_path: str = typer.Argument(..., help="Path to pipeline file (e.g. main.nf, Snakefile, script.sh)"),
) -> None:
    """Analyze and explain a bioinformatics pipeline script."""
    from pathlib import Path
    
    print_header()
    path = Path(file_path)
    if not path.exists():
        print_error(f"File not found: {file_path}")
        raise typer.Exit(1)
        
    code_content = path.read_text(encoding="utf-8")
    prompt = f"I have a bioinformatics script named {path.name}. Please explain what it does step by step, what tools it uses, and what inputs/outputs it expects. Here is the code:\n\n```{path.suffix}\n{code_content}\n```"
    
    config = Config.load()
    runtime = _build_runtime(config)
    
    from biopipe.core.ui import StreamingMarkdownPrinter
    printer = StreamingMarkdownPrinter()
    print_info("Analyzing script logic in air-gapped LLM...")
    
    try:
        result = asyncio.run(runtime.run(prompt, stream_callback=printer.append))
    except Exception as exc:
        printer.finalize()
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        asyncio.run(runtime.shutdown())

    printer.finalize()
    print_success(f"Explanation for {path.name}:")

@app.command("debug")
def debug(
    log_path: str = typer.Argument(..., help="Path to error log or stderr dump (e.g. slurm.out)"),
    lines: int = typer.Option(200, help="Number of tail lines to read"),
) -> None:
    """Read a crash log and suggest the fix for bio-pipelines."""
    from pathlib import Path
    
    print_header()
    path = Path(log_path)
    if not path.exists():
        print_error(f"Log not found: {log_path}")
        raise typer.Exit(1)
        
    # Read last N lines
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content_lines = f.readlines()
    tail = "".join(content_lines[-lines:])
    
    prompt = f"My bioinformatics pipeline crashed. Here are the last {lines} lines of the log file ({path.name}). Please identify the root cause of the error (e.g. OOM, syntax, missing index, missing file) and provide the exact commands or changes to fix it:\n\n```log\n{tail}\n```"
    
    config = Config.load()
    runtime = _build_runtime(config)
    
    from biopipe.core.ui import StreamingMarkdownPrinter
    printer = StreamingMarkdownPrinter()
    print_info("Debugging crash log...")
    
    try:
        result = asyncio.run(runtime.run(prompt, stream_callback=printer.append))
    except Exception as exc:
        printer.finalize()
        print_error(str(exc))
        raise typer.Exit(1)
    finally:
        asyncio.run(runtime.shutdown())

    printer.finalize()
    print_success(f"Debug Analysis for {path.name}:")


@app.command()
def setup() -> None:
    """Download and configure a local LLM model for BioPipe-CLI."""
    from biopipe.setup_wizard import run_setup
    run_setup()


@app.command()
def interactive(
    model: str = typer.Option(None, "--model", "-m", help="Ollama model name"),
) -> None:
    """Start interactive assistant mode (REPL)."""
    from biopipe.repl import BioPipeREPL

    config = Config.load()
    if model:
        config.model = model

    repl = BioPipeREPL(config)
    repl.start()


@app.command()
def health() -> None:
    """Check system health (Ollama connectivity, etc.)."""
    config = Config.load()
    runtime = _build_runtime(config)

    checks = asyncio.run(runtime.health_check())

    for component, status in checks.items():
        icon = "OK" if status else "FAIL"
        typer.echo(f"  [{icon}] {component}")

    if not all(checks.values()):
        raise typer.Exit(1)

    typer.echo("\nAll systems operational.")


@app.command()
def feedback(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Original request prompt"),
    rating: int = typer.Option(..., "--rating", "-r", help="Rating from 1 to 5"),
    text: str = typer.Argument(..., help="Feedback text describing what was wrong or right")
) -> None:
    """Submit RLHF feedback for fine-tuning the local model."""
    from biopipe.core.rlhf import RLHFDataStore
    
    if rating < 1 or rating > 5:
        print_error("Rating must be between 1 and 5")
        raise typer.Exit(1)
        
    store = RLHFDataStore()
    store.log_feedback(prompt=prompt, script="<not provided in CLI currently>", rating=rating, feedback_text=text)
    
    print_success("Feedback securely stored in local RLHF dataset.")


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
            typer.echo(f"No plugins found in {plugin_dir}")
            typer.echo("See PLUGIN_GUIDE.md for how to create plugins.")
            return
        for m in manifests:
            typer.echo(f"  {m.name} v{m.version} — {m.description}")
            if m.tools:
                typer.echo(f"    Tools: {', '.join(m.tools)}")
            if m.hooks:
                typer.echo(f"    Hooks: {', '.join(m.hooks)}")

    elif action == "info" and name:
        manifests = loader.discover()
        found = [m for m in manifests if m.name == name]
        if not found:
            typer.echo(f"Plugin '{name}' not found.")
            raise typer.Exit(1)
        m = found[0]
        typer.echo(f"Name:        {m.name}")
        typer.echo(f"Version:     {m.version}")
        typer.echo(f"Author:      {m.author}")
        typer.echo(f"Description: {m.description}")
        typer.echo(f"Entry point: {m.entry_point}")
        typer.echo(f"Tools:       {', '.join(m.tools) or '(none)'}")
        typer.echo(f"Hooks:       {', '.join(m.hooks) or '(none)'}")
        typer.echo(f"Permissions: {', '.join(m.permissions) or '(none)'}")

    elif action == "validate" and name:
        import json
        from biopipe.core.plugin_sdk import PluginManifest
        from biopipe.core.errors import PermissionDeniedError, ToolValidationError

        manifest_path = Path(name) / "manifest.json"
        if not manifest_path.exists():
            typer.echo(f"No manifest.json found in {name}")
            raise typer.Exit(1)

        try:
            data = json.loads(manifest_path.read_text())
            manifest = PluginManifest(**{
                k: data.get(k, v.default if hasattr(v, 'default') else "")
                for k, v in PluginManifest.__dataclass_fields__.items()
            })
            loader._validate_manifest(manifest)
            typer.echo(f"  Manifest: OK")

            if manifest.entry_point:
                result = loader.load_plugin(manifest)
                typer.echo(f"  Import:   OK")
                typer.echo(f"  Tools:    {len(result['tools'])} loaded")
                typer.echo(f"  Hooks:    {len(result['hooks'])} loaded")
            typer.echo(f"\n  Plugin '{manifest.name}' is valid.")
        except PermissionDeniedError as exc:
            typer.echo(f"  REJECTED: {exc}", err=True)
            raise typer.Exit(1)
        except ToolValidationError as exc:
            typer.echo(f"  INVALID: {exc}", err=True)
            raise typer.Exit(1)
        except Exception as exc:
            typer.echo(f"  ERROR: {exc}", err=True)
            raise typer.Exit(1)

    elif action == "install" and name:
        import subprocess
        plugin_url = name
        plugin_name = plugin_url.rstrip("/").split("/")[-1]
        if plugin_name.endswith(".git"):
            plugin_name = plugin_name[:-4]
            
        target_dir = Path(plugin_dir) / plugin_name
        if target_dir.exists():
            typer.echo(f"Plugin directory {target_dir} already exists.", err=True)
            raise typer.Exit(1)
            
        typer.echo(f"Cloning {plugin_url} into {target_dir}...")
        Path(plugin_dir).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", plugin_url, str(target_dir)], 
                capture_output=True, text=True, check=True
            )
            typer.echo(f"Successfully installed plugin '{plugin_name}'.")
            typer.echo(f"Run `biopipe plugins validate {target_dir}` to verify.")
        except subprocess.CalledProcessError as exc:
            typer.echo(f"Failed to clone repository:\n{exc.stderr}", err=True)
            raise typer.Exit(1)
        except FileNotFoundError:
            typer.echo("Git is not installed or not in PATH.", err=True)
            raise typer.Exit(1)

    else:
        typer.echo("Usage: biopipe plugins [list|info <name>|validate <path>|install <git_url>]")


def main() -> None:
    """Entry point for pip install console_scripts."""
    app()


if __name__ == "__main__":
    main()
