# Contributing to BioPipe-CLI

Thank you for considering contributing to BioPipe-CLI! This project aims to make bioinformatics pipeline generation safe, fast, and local.

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) (for running the local LLM)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/biopipe-cli.git
cd biopipe-cli

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install in development mode with all extras
pip install -e ".[dev,rag]"
pip install wasmtime  # For WASM plugin support

# Run tests
pytest tests/ -v
```

### Project Layout

```
src/biopipe/
├── core/            # Security engine, agent loop, plugin SDK
│   ├── safety.py         # 10-layer script validator
│   ├── wasm_runner.py    # WASM plugin sandbox (Wasmtime)
│   ├── critic.py         # Multi-Agent Debate (Critic Agent)
│   ├── snapshots.py      # Time-Travel debugger
│   └── ...
├── llm/             # LLM providers (Ollama, OpenAI-compatible)
├── rag/             # ChromaDB RAG + anti-poisoning
├── generators/      # NGS script templates
└── cli.py           # Typer CLI entry point

tests/               # 217+ tests
plugins/             # Example plugins (Python + WASM)
```

## 🧪 Running Tests

```bash
# Full suite
pytest tests/ -v

# Specific test file
pytest tests/test_wasm_sandbox.py -v

# With coverage (if installed)
pytest tests/ --cov=biopipe --cov-report=html
```

All 217+ tests must pass before submitting a PR.

## 📝 Code Style

We use **Ruff** for linting and formatting:

```bash
ruff check src/        # Lint
ruff format src/       # Format
```

Configuration is in `pyproject.toml`. Key rules:
- Line length: 100 characters
- Target: Python 3.11+
- All code must be type-hinted

## 🔐 Security Model

BioPipe-CLI treats the LLM as an **untrusted text generator**. If your change touches security:

1. Every script output passes through `SafetyValidator` — **no exceptions**
2. Plugins are capped at `GENERATE` permission — **never EXECUTE**
3. WASM plugins run in mathematically isolated memory — **verify with tests**
4. Session injection is blocked by `SessionManager.restore()` — **don't weaken it**

**Write a Red Team test** for any new security-relevant code. See `tests/test_security_hardening.py` for examples.

## 🔌 Writing Plugins

See the [Plugin Developer Guide](PLUGIN_GUIDE.md) for both Python and WASM plugin paths.

**TL;DR:**
- Python plugins: create `plugins/biopipe_<name>/manifest.json` + Python package
- WASM plugins: write in Rust/Go, compile to `.wasm`, export `allocate/execute/get_result_ptr/get_result_len`

## 🔄 Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for your changes
4. Ensure all tests pass: `pytest tests/ -v`
5. Ensure linting passes: `ruff check src/`
6. Commit with descriptive messages
7. Open a PR against `main`

### PR Checklist

- [ ] Tests pass (`pytest tests/ -v`)
- [ ] Linting passes (`ruff check src/`)
- [ ] New features have tests
- [ ] Security-relevant changes include Red Team tests
- [ ] Documentation updated if needed

## 📜 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
