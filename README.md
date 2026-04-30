# BioPipe CLI Monorepo

## Overview
This repository stores multiple snapshots and packaging variants of **BioPipe-CLI**.

The active CLI command surface includes (among others):
- `generate`
- `plugins`
- `index-security`
- `feedback`

## Source of Truth

> **Canonical source for development in this repo: `versions/v0.5.0-enterprise/`**

Use `versions/v0.5.0-enterprise/` as the primary editable codebase for implementation changes.

Other directories are distribution or mirror artifacts and should be treated as derived unless you are doing release/packaging-specific work.

## Repository Layout
- `versions/v0.5.0-enterprise/` — **main editable implementation (source of truth)**
- `versions/v0.5.0-github-ready/` — GitHub-facing packaged snapshot
- `versions/v0.4.0/` — older snapshot
- `current/` — synchronized/derived working artifact
- `archives/` — archived materials

## Developer Guardrail: Edit Here vs Generated Artifact

| Edit here (authoritative) | Generated artifact / mirror | Notes |
|---|---|---|
| `versions/v0.5.0-enterprise/src/**` | `current/src/**`, `versions/v0.5.0-github-ready/src/**` | Core Python source changes should start in enterprise tree. |
| `versions/v0.5.0-enterprise/tests/**` | `current/tests/**`, `versions/v0.5.0-github-ready/tests/**` | Tests should be updated in source-of-truth tree first. |
| `versions/v0.5.0-enterprise/plugins/**` | `current/plugins/**`, `versions/v0.5.0-github-ready/plugins/**` | Plugin examples and demo artifacts originate here. |
| `versions/v0.5.0-enterprise/*.md` | `current/*.md`, `versions/v0.5.0-github-ready/*.md` | Product/docs updates should begin in canonical docs. |

## CLI Command Examples (verified against current CLI)

### Generate
```bash
# One-shot generation
biopipe generate "RNA-seq pipeline for mouse, paired-end, HISAT2"

# Interactive mode
biopipe interactive
```

### Plugins
```bash
# List plugins
biopipe plugins list

# Validate local plugin
biopipe plugins validate ./my-plugin
```

### Index security
```bash
biopipe index-security
```

### Feedback
```bash
biopipe feedback -p "Generate WGS pipeline" -r 5 "Perfect output"
```

## Quick Validation
To inspect the command list exposed by the current CLI module:

```bash
PYTHONPATH=versions/v0.5.0-enterprise/src python -m biopipe.cli --help
```

The output includes `generate`, `plugins`, `index-security`, and `feedback`.
