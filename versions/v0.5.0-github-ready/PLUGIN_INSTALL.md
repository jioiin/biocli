# BioPipe-CLI: Installing Plugins

BioPipe-CLI core has **zero built-in tools**. All capabilities come from plugins.
This is by design — the core handles security, routing, and logging. Everything
domain-specific (NGS, Opentrons, SLURM) lives in separate repos.

## Installing a Plugin

Every plugin is a git repository with a `manifest.json` and a Python package.

```bash
# 1. Clone the plugin into ~/.biopipe/plugins/
git clone https://github.com/biopipe/biopipe-plugin-ngs ~/.biopipe/plugins/biopipe-plugin-ngs

# 2. Install Python dependencies (if any)
cd ~/.biopipe/plugins/biopipe-plugin-ngs
pip install -e .

# 3. Verify
biopipe plugins list
# Output:
#   biopipe-plugin-ngs v1.0.0 — NGS pipeline generator (RNA-seq, WGS, ATAC-seq)
#     Tools: ngs_pipeline
```

That's it. On next `biopipe interactive` or `biopipe generate`, the plugin is
automatically discovered and loaded.

## How It Works

```
~/.biopipe/plugins/
├── biopipe-plugin-ngs/          # git clone'd repo
│   ├── manifest.json
│   ├── biopipe_plugin_ngs/
│   │   └── __init__.py          # Tool classes
│   └── setup.py
├── biopipe-plugin-slurm/        # another plugin
│   ├── manifest.json
│   └── ...
└── biopipe-plugin-opentrons/    # another plugin
    └── ...

At startup:
  BioPipe-CLI scans ~/.biopipe/plugins/*/manifest.json
  → validates each manifest (no forbidden permissions)
  → imports entry_point Python package
  → validates each Tool class (permission ≤ GENERATE)
  → registers tools in ToolRegistry
  → LLM sees all tools via function calling schema
```

## Official Plugins (maintained by BioPipe team)

| Plugin | Repo | What it does |
|--------|------|-------------|
| `biopipe-plugin-ngs` | `github.com/biopipe/biopipe-plugin-ngs` | RNA-seq, WGS/WES, ATAC-seq, ChIP-seq pipeline generation |
| `biopipe-plugin-slurm` | `github.com/biopipe/biopipe-plugin-slurm` | SLURM #SBATCH header generation for HPC |
| `biopipe-plugin-opentrons` | `github.com/biopipe/biopipe-plugin-opentrons` | Opentrons robot Python scripts |

## Community Plugins

Anyone can write a plugin. See `PLUGIN_GUIDE.md` for the full development guide.

## Updating a Plugin

```bash
cd ~/.biopipe/plugins/biopipe-plugin-ngs
git pull
pip install -e .  # if dependencies changed
```

## Removing a Plugin

```bash
rm -rf ~/.biopipe/plugins/biopipe-plugin-ngs
```

## Plugin Security

Plugins CANNOT:
- Execute scripts (max permission: GENERATE)
- Access network (curl, wget, socket — blocked)
- Read environment variables (API keys, tokens)
- Modify core modules
- Bypass the 10-layer safety validator
- Self-approve actions

Every plugin's output passes through the same SafetyValidator as core output.
If a plugin generates `rm -rf /`, safety blocks it. Period.
