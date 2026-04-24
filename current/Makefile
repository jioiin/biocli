.PHONY: install dev test lint security clean build

## Install for end users
install:
	pip install .

## Install for development
dev:
	pip install -e ".[dev,rag,wasm]"

## Run full test suite
test:
	PYTHONPATH=src pytest tests/ -v --tb=short

## Run linter
lint:
	ruff check src/
	ruff format --check src/

## Run security scanner
security:
	bandit -r src/biopipe/ -f json -o bandit-report.json || true
	@echo "Report saved to bandit-report.json"

## Build distribution
build:
	python -m build

## Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

## Show help
help:
	@echo "Available commands:"
	@echo "  make install    - Install biopipe-cli"
	@echo "  make dev        - Install with dev dependencies"
	@echo "  make test       - Run 217+ tests"
	@echo "  make lint       - Run ruff linter"
	@echo "  make security   - Run bandit security scan"
	@echo "  make build      - Build PyPI distribution"
	@echo "  make clean      - Remove build artifacts"
