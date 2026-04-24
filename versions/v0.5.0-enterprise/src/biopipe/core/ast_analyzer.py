"""Python AST analyzer for generated code safety.

Catches dangerous patterns that regex misses: obfuscated calls,
dynamic imports, attribute-based system access.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ASTViolation:
    """Single AST-level safety issue."""
    node_type: str
    line: int
    description: str
    severity: str


_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "os", "subprocess", "shutil",
    "socket", "urllib", "http", "requests",
    "ftplib", "smtplib", "xmlrpc",
    "pickle", "shelve", "marshal",
    "ctypes", "cffi",
    "importlib", "runpy",
    "code", "codeop", "compileall",
})

_BLOCKED_CALLS: frozenset[str] = frozenset({
    "eval", "exec", "compile",
    "globals", "locals", "__import__",
    "getattr", "setattr", "delattr",
})

_DANGEROUS_ATTRS: frozenset[str] = frozenset({
    "os.system", "os.popen", "os.execvp", "os.spawn",
    "subprocess.call", "subprocess.run",
    "subprocess.Popen", "subprocess.check_output",
    "shutil.rmtree",
})


class PythonASTAnalyzer:
    """Analyze Python code via AST, not regex."""

    def analyze(self, code: str) -> list[ASTViolation]:
        """Parse and check for violations."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [ASTViolation("SyntaxError", e.lineno or 0,
                                 f"Unparseable: {e.msg}", "critical")]

        violations: list[ASTViolation] = []
        for node in ast.walk(tree):
            violations.extend(self._check_node(node))
        return violations

    def _check_node(self, node: ast.AST) -> list[ASTViolation]:
        vs: list[ASTViolation] = []

        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_IMPORTS:
                    vs.append(ASTViolation(
                        "Import", node.lineno,
                        f"Blocked import: {alias.name}", "critical"))

        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _BLOCKED_IMPORTS:
                vs.append(ASTViolation(
                    "ImportFrom", node.lineno,
                    f"Blocked: from {node.module}", "critical"))

        elif isinstance(node, ast.Call):
            name = self._call_name(node)
            if name in _BLOCKED_CALLS:
                vs.append(ASTViolation(
                    "Call", node.lineno,
                    f"Blocked call: {name}()", "critical"))

        elif isinstance(node, ast.Attribute):
            full = self._attr_chain(node)
            if any(full.startswith(d) for d in _DANGEROUS_ATTRS):
                vs.append(ASTViolation(
                    "Attribute", node.lineno,
                    f"Blocked: {full}", "critical"))

        return vs

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    @staticmethod
    def _attr_chain(node: ast.Attribute) -> str:
        parts = [node.attr]
        cur = node.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
