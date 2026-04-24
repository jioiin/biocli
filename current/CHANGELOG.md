# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] — 2026-04-14

### Added

- **WASM Plugin Sandbox** — Third-party plugins now run inside Wasmtime VMs with mathematical memory isolation, zero FS/network access, and CPU fuel budgets. Plugins can be written in Rust, Go, or C and compiled to `.wasm`.
- **Multi-Agent Debate** — Critic Agent reviews generated scripts before output. If rejected, the Time-Travel Debugger rewinds the session and forces the main agent to fix its logic.
- **Time-Travel Debugger** — `TimeTravelDebugger` takes snapshots at each agent iteration. On Critic rejection, the session is rewound to the snapshot, discarding hallucinated output.
- **DAG Topology Analyzer** — Detects circular dependencies in Snakemake rules before scripts are submitted to HPC clusters.
- **MultiQC AI Insights** — Parses `multiqc_data.json` and generates human-readable QC summaries using the local LLM.
- **NF-Core Sync** — Fetches nf-core pipeline registry for RAG documentation indexing.
- **RLHF Feedback** — `biopipe feedback` command stores user ratings in JSONL format for future fine-tuning (DPO/RLHF).
- **Privacy Scrubber** — Redacts emails, SSNs, patient IDs, and genomic variants from logs (HIPAA compliance).
- **Anti-RAG Poisoning** — `RAGPoisonDetector` uses a secondary LLM to screen retrieved documents for malicious instructions before injecting them into the agent context.

### Changed

- Bumped version to 0.5.0 (Enterprise).
- `pyproject.toml` now includes `[wasm]` and `[all]` optional dependency groups.
- GitHub Actions CI matrix: tests across Python 3.11/3.12 on Ubuntu, Windows, macOS.

### Fixed

- Fixed `ctypes` pointer arithmetic for Wasmtime `data_ptr()` — `LP_c_ubyte` now correctly cast to `c_void_p` before offset addition.
- Fixed `datetime.utcnow()` deprecation warning in `rlhf.py`.
- Fixed `MockLLM.generate()` missing `**kwargs` causing test failures.

## [0.4.0] — 2026-04-13

### Added

- Red Team security test suite (session injection, cloud model blocking, config immutability).
- 10-layer `SafetyValidator` with AST analysis, network exfiltration detection, and SLURM limits.
- `SessionManager` with injection-resistant `restore()`.
- RAG retrieval via ChromaDB.
- Plugin SDK with permission model.

## [0.1.0] — 2026-04-12

### Added

- Initial release.
- Core agent loop with Ollama integration.
- Script generation for RNA-seq, WGS, QC.
- Typer CLI with `generate`, `health`, `index` commands.
