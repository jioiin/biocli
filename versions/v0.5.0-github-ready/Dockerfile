# BioPipe-CLI Docker Image
# Usage:
#   docker build -t biopipe-cli .
#   docker run -it --network host biopipe-cli generate "QC for paired-end FASTQ"
#
# Note: Ollama must be running on the host (--network host gives access to localhost:11434)

FROM python:3.12-slim AS base

LABEL maintainer="BioPipe Contributors"
LABEL description="Local AI agent for bioinformatics pipeline generation"
LABEL version="0.5.0"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash biopipe
USER biopipe
WORKDIR /home/biopipe/app

# Install Python dependencies first (cached layer)
COPY --chown=biopipe:biopipe pyproject.toml README.md ./
COPY --chown=biopipe:biopipe src/ src/
RUN pip install --user --no-cache-dir ".[rag,wasm]"

# Copy the rest
COPY --chown=biopipe:biopipe plugins/ plugins/
COPY --chown=biopipe:biopipe tests/ tests/

# Add user pip bin to PATH
ENV PATH="/home/biopipe/.local/bin:${PATH}"
ENV PYTHONPATH="/home/biopipe/app/src"

# Default: show help
ENTRYPOINT ["biopipe"]
CMD ["--help"]
