#!/usr/bin/env python3
"""
CI/CD Security Gate

Runs AST analysis and Bandit SAST over the src/ directory.
Fails the build if any High/Medium security vulnerabilities are found.
"""

import sys
import subprocess
from pathlib import Path

def run_bandit():
    print("[*] Running Bandit SAST scanner...")
    try:
        # Run bandit. -ll means only medium and high severity.
        result = subprocess.run(
            ["bandit", "-r", "src/", "-ll", "-i"], 
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print("❌ Bandit found potential security issues:")
            print(result.stdout)
            return False
        else:
            print("✅ Bandit passing. No medium/high issues found.")
            return True
    except FileNotFoundError:
        print("❌ Bandit not installed. Run: pip install bandit")
        return False

def run_ast_vibe_check():
    """Custom AST checks that Vibe-Shield or 3stoneBrother check for."""
    print("[*] Running AST integrity checks on core layers...")
    
    # Example logic: Verify no core python files use raw exec/eval. 
    # (Though Bandit catches this, this is a placeholder for Agentic AI pipeline specific checks).
    src_dir = Path("src/biopipe/core")
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "eval(" in content or "exec(" in content:
            # check if it's nosec
            if "nosec" not in content.split("eval(")[1].split("\n")[0]:
                print(f"❌ Unsafe eval/exec found in {py_file} without # nosec annotation.")
                return False
    print("✅ AST Integrity checks passed.")
    return True

if __name__ == "__main__":
    b_pass = run_bandit()
    ast_pass = run_ast_vibe_check()
    
    if b_pass and ast_pass:
        print("\n🚀 Security Gate PASSED. Ready for commit/merge.")
        sys.exit(0)
    else:
        print("\n💥 Security Gate FAILED. Please fix the vulnerabilities.")
        sys.exit(1)
