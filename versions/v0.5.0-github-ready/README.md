<div align="center">

# 🧬 BioPipe-CLI

**AI-powered bioinformatics pipeline generator that runs 100% locally.**

[![CI](https://github.com/YOUR_USERNAME/biopipe-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/biopipe-cli/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/biopipe-cli.svg?color=blue)](https://pypi.org/project/biopipe-cli/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-217%20passed-brightgreen.svg)](#)
[![Security](https://img.shields.io/badge/security-10%20layer%20validator-red.svg)](#-security-architecture)

*Translate natural language into production-ready NGS scripts. No cloud APIs. No data leakage. HIPAA-safe by design.*

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 🏠 **100% Local** | Runs Ollama on localhost. Your genomic data never leaves your machine. |
| 🛡️ **10-Layer Safety** | Every script passes regex, AST, path traversal, network, and SLURM validators. |
| 🔌 **WASM Plugin Sandbox** | Third-party plugins run in mathematically isolated WebAssembly VMs. |
| 🤖 **Multi-Agent Debate** | A Critic Agent reviews scripts before output. Bad logic triggers Time-Travel rewind. |
| 📚 **RAG-Powered** | Indexes man pages & tool docs via ChromaDB to reduce flag hallucination. |
| 🧬 **NGS-First** | RNA-seq, WGS, ChIP-seq, ATAC-seq with correct tool flags and best practices. |
| 🔒 **HIPAA-Ready** | Built-in PHI redaction, differential privacy scrubber, audit logging. |

---

## 🚀 Quick Start

### One-Line Install

```bash
pip install biopipe-cli
```

### From Source (Development)

```bash
git clone https://github.com/YOUR_USERNAME/biopipe-cli.git
cd biopipe-cli
pip install -e ".[dev,rag]"
```

### Prerequisites

1. **Python 3.11+**
2. **Ollama** — [Install Ollama](https://ollama.ai), then:

```bash
ollama pull qwen2.5-coder:7b    # Recommended model
ollama serve                      # Start server (separate terminal)
```

### First Run

```bash
# Interactive setup wizard
biopipe setup

# Generate a QC pipeline
biopipe generate "QC for paired-end FASTQ files from Illumina NovaSeq"

# RNA-seq pipeline
biopipe generate "RNA-seq pipeline for mouse, paired-end, HISAT2 aligner, hg38"

# Check system health
biopipe health
```

### Example Output

```bash
#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# BioPipe-CLI Generated Script
# Date:     2026-04-14 11:30 UTC
# Model:    qwen2.5-coder:7b
# Prompt:   "QC for paired-end FASTQ files"
# SHA-256:  a3f8c2...
# ============================================================

SAMPLE_R1="sample_R1.fastq.gz"       # Forward reads
SAMPLE_R2="sample_R2.fastq.gz"       # Reverse reads
THREADS=4                             # CPU threads

fastqc \
  --threads "${THREADS}" \            # Parallel threads
  --outdir "./qc_raw" \              # Output directory
  "${SAMPLE_R1}" "${SAMPLE_R2}"       # Input FASTQ files

multiqc ./qc_raw -o ./multiqc_report  # Aggregate QC reports
```

---

## 🏗️ Architecture

```
User prompt → Input Sandbox → RAG Retrieval → LLM (Ollama)
                                                    │
                                              Critic Agent ←── Time-Travel Debugger
                                                    │
                                              Safety Validator (10 layers)
                                                    │
                                                 Output
```

### Core Modules

```
src/biopipe/
├── core/                          # 40+ modules
│   ├── safety.py                       # 10-layer script validator
│   ├── wasm_runner.py                  # WASM sandbox (Wasmtime)
│   ├── critic.py                       # Multi-Agent Debate
│   ├── snapshots.py                    # Time-Travel state debugger
│   ├── plugin_sdk.py                   # Plugin loader (Python + WASM)
│   ├── privacy.py                      # HIPAA PHI redaction
│   ├── dag_parser.py                   # Snakemake/NF cycle detection
│   ├── rlhf.py                         # RLHF feedback collector
│   ├── loop.py                         # Agent loop
│   └── ...
├── llm/                           # Ollama + OpenAI-compatible providers
├── rag/                           # ChromaDB + anti-RAG poisoning
└── cli.py                         # Typer CLI
```

---

## 🛡️ Security Architecture

BioPipe-CLI treats the LLM as an **untrusted text generator**. Every output passes through deterministic Python validation that cannot be bypassed by prompt injection.

### 10-Layer Safety Validator

| # | Layer | What it catches |
|---|-------|-----------------|
| 1 | Regex blocklist | `rm -rf`, `sudo`, `chmod 777`, `eval()` |
| 2 | Obfuscation detection | `r\m`, hex encoding, base64→shell pipes |
| 3 | Network exfiltration | `curl`, `wget`, DNS exfiltration via `ping` |
| 4 | Dependency squatting | `pip install`, `conda install` inside scripts |
| 5 | Path traversal | `../`, `~/.bashrc`, `/etc/` |
| 6 | SLURM limits | `--nodes > 4`, `--time > 72h` |
| 7 | Shell metacharacters | Unquoted `$VARIABLES` |
| 8 | Python AST analysis | `os.system()`, `subprocess`, `pickle.load()` |
| 9 | Tool allowlist | Unknown bioinformatics tools flagged |
| 10 | Best practices | Missing `set -euo pipefail`, shebang |

### WASM Plugin Sandbox

Third-party plugins run in a **WebAssembly VM** (Wasmtime) with:
- ❌ Zero filesystem access
- ❌ Zero network access
- ✅ Linear memory isolation (can't read host memory)
- ✅ CPU fuel budget (infinite loops terminated)

### Session Security

- Input sanitization strips prompt injection attempts
- Session restore blocks rogue `system` messages
- Cloud model endpoints are blocked (local-only enforcement)

---

## 🔌 Plugins

BioPipe supports two plugin types:

| | Python Plugin | WASM Plugin |
|---|---|---|
| **Language** | Python | Rust, Go, C |
| **Memory Isolation** | ❌ Shared process | ✅ Mathematical |
| **Use case** | Internal/trusted | Community/third-party |

```bash
# List plugins
biopipe plugins list

# Validate a plugin
biopipe plugins validate ./my-plugin/

# Submit feedback for RLHF
biopipe feedback -p "Generate WGS pipeline" -r 5 "Perfect output"
```

See [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) for the full developer guide.

---

## ⚙️ Configuration

BioPipe reads config from (highest priority first):

1. CLI arguments (`--model`, `--output-dir`)
2. Environment variables
3. Project file `biopipe.toml`
4. Defaults

```bash
export BIOPIPE_OLLAMA_URL="http://localhost:11434"
export BIOPIPE_MODEL="qwen2.5-coder:7b"
export BIOPIPE_OUTPUT_DIR="./results"
```

---

## 🧪 Testing

```bash
# Full suite (217+ tests)
pytest tests/ -v

# Security tests only
pytest tests/test_security_hardening.py tests/test_safety.py -v

# WASM sandbox tests
pytest tests/test_wasm_sandbox.py -v
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR guidelines.

---

## 📄 License

[MIT](LICENSE) — free for academic and commercial use.

---

<div align="center">
<sub>Built for bioinformaticians who care about reproducibility and data sovereignty.</sub>
</div>
