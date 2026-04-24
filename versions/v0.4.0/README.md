# BioPipe-CLI

**Local AI agent for bioinformatics pipeline generation.**

BioPipe-CLI translates natural language into production-ready bash scripts for NGS data analysis. It runs entirely on your machine — no data leaves your environment.

## Key Features

- **Local LLM** — Ollama (Llama-3 8B) runs on localhost. No cloud API, no data leakage.
- **Dry-run only** — Generates scripts for review, never executes them.
- **10-layer safety validator** — Blocks `rm -rf`, `sudo`, network calls, path traversal, obfuscated commands, and more. Every script passes through deterministic safety checks before you see it.
- **RAG-powered** — Indexes man pages and tool documentation locally via ChromaDB. Reduces flag hallucination by grounding generation in real documentation.
- **NGS pipelines** — RNA-seq, WGS/WES variant calling, ATAC-seq, ChIP-seq with correct tool flags and best practices.
- **Commented output** — Every flag in every generated script has a comment explaining what it does.
- **Reproducibility** — Each script includes metadata: generation date, model ID, prompt summary.

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- 16+ GB RAM (for Llama-3 8B Q4)

### Install

```bash
# 1. Install Ollama and pull a model
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3:8b-instruct-q4_K_M
ollama serve  # run in a separate terminal

# 2. Install BioPipe-CLI
pip install -e .

# 3. Optional: install RAG support
pip install -e ".[rag]"
```

### Usage

```bash
# Generate a QC pipeline
biopipe generate "QC for paired-end FASTQ files"

# RNA-seq pipeline
biopipe generate "RNA-seq pipeline for mouse, paired-end, HISAT2 aligner"

# WGS variant calling
biopipe generate "WGS variant calling pipeline, hg38, paired-end Illumina"

# Index tool documentation for better generation
biopipe index samtools bwa fastqc gatk hisat2 fastp

# Check system health
biopipe health
```

### Example Output

```bash
#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# BioPipe-CLI Generated Script
# Date:     2026-04-12 14:30 UTC
# Model:    llama3:8b-instruct-q4_K_M
# Prompt:   "QC for paired-end FASTQ files"
# Pipeline: QC Only
# ============================================================

SAMPLE_R1="sample_R1.fastq.gz"       # Forward reads
SAMPLE_R2="sample_R2.fastq.gz"       # Reverse reads
OUTPUT_DIR="./biopipe_output"         # Output directory
THREADS=4                             # Number of threads

fastqc \
  --threads "${THREADS}" \            # Parallel threads for analysis
  --outdir "${OUTPUT_DIR}/qc_raw" \   # Output directory for QC reports
  "${SAMPLE_R1}" "${SAMPLE_R2}"       # Input FASTQ files
```

## Architecture

```
User prompt → Input Sandbox → RAG Retrieval → LLM (Ollama) → Safety Validator → Output
                    │                                              │
            Strip injections                              10-layer check:
            Score risk 0–1.0                              regex, AST, paths,
                                                          network, SLURM,
                                                          allowlist, obfuscation
```

The core treats the LLM as an **untrusted text generator**. Every output passes through deterministic Python validation that cannot be bypassed by prompt injection.

### Safety Layers

| # | Layer | What it catches |
|---|-------|-----------------|
| 1 | Regex blocklist | `rm -rf`, `sudo`, `chmod 777`, `eval()` |
| 2 | Obfuscation detection | `r\m`, hex encoding, base64 decode piped to shell |
| 3 | Network exfiltration | `curl`, `wget`, `ping` (DNS exfiltration), Python `socket` |
| 4 | Dependency squatting | `pip install`, `conda install` inside scripts |
| 5 | Path traversal | `../`, `~/.bashrc`, `/etc/`, absolute paths |
| 6 | SLURM limits | `--nodes > 4`, `--time > 72h` |
| 7 | Shell metacharacters | Unquoted `$VARIABLES` |
| 8 | Python AST | `os.system()`, `subprocess`, `pickle.load()` via AST walk |
| 9 | Tool allowlist | Unknown bioinformatics tools flagged |
| 10 | Best practices | Missing `set -euo pipefail`, shebang, metadata header |

## Project Structure

```
src/biopipe/
├── core/           # Security, routing, logging (16 modules)
│   ├── safety.py        # 10-layer validator
│   ├── sandbox.py       # Input sanitization
│   ├── ast_analyzer.py  # Python AST analysis
│   ├── loop.py          # Agent loop (prompt→LLM→safety→output)
│   ├── runtime.py       # DI container
│   └── ...
├── llm/            # Ollama client + system prompts
├── rag/            # ChromaDB indexing + retrieval
├── generators/     # NGS script templates
└── cli.py          # Typer entry point
```

## Configuration

BioPipe-CLI reads configuration from (highest priority first):

1. CLI arguments (`--model`, `--output-dir`)
2. Environment variables (`BIOPIPE_MODEL`, `BIOPIPE_OLLAMA_URL`)
3. Project file `biopipe.toml`
4. Defaults

```bash
# Environment variables
export BIOPIPE_OLLAMA_URL="http://localhost:11434"
export BIOPIPE_MODEL="llama3:8b-instruct-q4_K_M"
export BIOPIPE_OUTPUT_DIR="./results"
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 89+ tests
ruff check src/           # linting
mypy src/                 # type checking
```

## Why Python?

Bioinformaticians know Python. The entire ecosystem (LangChain, ChromaDB, BioPython, pysam) is Python. A Rust/Go CLI would require FFI bridges to Python libraries — 3x development time for zero user benefit. The target audience does `pip install`, not `cargo build`.

## Why Local LLM?

HIPAA classifies genomic data as PHI. A tool that sends prompts to cloud APIs (even without raw data) creates compliance exposure. BioPipe-CLI runs Ollama on localhost — no network calls, no BAA required, no GDPR cross-border issues.

## License

MIT
