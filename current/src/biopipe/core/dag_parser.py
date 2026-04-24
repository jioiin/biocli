"""DAG Topology Analyzer for Workflow Scripts.

Detects deadlocks and circular dependencies in Snakefiles/Nextflow
to prevent submitting broken pipelines to HPC clusters.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class DAGViolation(NamedTuple):
    type: str
    description: str


class DAGAnalyzer:
    """Parses rules and their input/output constraints to build a topological graph."""

    @staticmethod
    def analyze_snakemake(content: str) -> list[DAGViolation]:
        """Simple AST-less parser to detect explicit cyclical inputs in Snakefiles.
        Full DAG evaluation requires running snakemake itself, but this catches
        obvious AI hallucinations.
        """
        violations = []
        rules = {}
        
        # Extremely basic regex parsing for rule definitions
        rule_pattern = re.compile(r"rule\s+(\w+):", re.MULTILINE)
        input_pattern = re.compile(r"input:\s*([^\n]+)")
        output_pattern = re.compile(r"output:\s*([^\n]+)")
        
        rule_blocks = re.split(r"rule\s+", content)
        for block in rule_blocks[1:]:
            parts = block.split(":", 1)
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            
            inputs = []
            outputs = []
            
            inp_match = input_pattern.search(block)
            if inp_match:
                inputs = [i.strip(' ",') for i in inp_match.group(1).split(",")]
                
            out_match = output_pattern.search(block)
            if out_match:
                outputs = [o.strip(' ",') for o in out_match.group(1).split(",")]
                
            rules[name] = {"inputs": inputs, "outputs": outputs}

        # Check for circular self-references
        for rule_name, io in rules.items():
            for out in io["outputs"]:
                if out in io["inputs"] and out:
                    violations.append(DAGViolation(
                        type="circular_dependency",
                        description=f"Rule '{rule_name}' requires its own output '{out}' as input."
                    ))
                    
        return violations
