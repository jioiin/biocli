"""10-layer deterministic safety validator.

LLM output passes through this BEFORE reaching the user.
Cannot be bypassed by prompt injection.
"""

from __future__ import annotations

import hashlib
import re

from .ast_analyzer import PythonASTAnalyzer
from .path_validator import PathValidator
from .types import SafetyReport, SafetyViolation

_BLOCKLIST: dict[str, str] = {
    r"rm\s+-(r|f|rf|fr)\b": "Recursive/force deletion",
    r"rm\b(?=[^\n]*\s--recursive\b)(?=[^\n]*\s--force\b)[^\n]*": "Recursive/force deletion",
    r"\bsudo\b": "Privilege escalation",
    r"\bchmod\s+777\b": "World-writable permissions",
    r"\bdd\s+if=": "Raw disk write",
    r"\bmkfs\b": "Filesystem format",
    r">\s*/dev/sd": "Direct device write",
    r":\(\)\{\s*:\|:&\s*\};:": "Fork bomb",
    r"\beval\s*\(": "eval() injection",
    r"\bexec\s*\(": "exec() injection",
    r"\b__import__\s*\(": "Dynamic import",
}

_OBFUSCATION: dict[str, str] = {
    r"r\\m": "Obfuscated rm",
    r"\$'\\x": "Hex-encoded shell command",
    r"base64\s+(--)?d(ecode)?": "Base64 decode (hidden command)",
    r"\$\(.*\).*\|\s*(ba)?sh": "Command substitution piped to shell",
    r"echo\s+.*\|\s*(ba)?sh": "Echo piped to shell",
    r"printf\s+.*\|\s*(ba)?sh": "Printf piped to shell",
}

_NETWORK: dict[str, str] = {
    r"\bcurl\b": "curl", r"\bwget\b": "wget",
    r"\bnc\b": "netcat", r"\bncat\b": "ncat",
    r"\btelnet\b": "telnet", r"\bssh\b": "ssh",
    r"\bscp\b": "scp", r"\brsync\b": "rsync",
    r"\bftp\b": "ftp",
    r"\bping\b": "DNS exfiltration via ping",
    r"\bdig\b": "DNS exfiltration via dig",
    r"\bnslookup\b": "DNS exfiltration via nslookup",
    r"import\s+socket": "Python socket",
    r"import\s+urllib": "Python urllib",
    r"import\s+requests": "Python requests",
    r"from\s+urllib": "Python urllib",
}

_INSTALL: dict[str, str] = {
    r"\bpip3?\s+install\b": "pip install",
    r"\bconda\s+install\b": "conda install",
    r"\bmamba\s+install\b": "mamba install",
    r"\bapt(-get)?\s+install\b": "apt install",
    r"\byum\s+install\b": "yum install",
    r"\bdnf\s+install\b": "dnf install",
}

_COMPILED_BLOCKLIST = [(re.compile(pat, re.IGNORECASE), pat, desc) for pat, desc in _BLOCKLIST.items()]
_COMPILED_OBFUSCATION = [(re.compile(pat, re.IGNORECASE), pat, desc) for pat, desc in _OBFUSCATION.items()]
_COMPILED_NETWORK = [(re.compile(pat, re.IGNORECASE), pat, desc) for pat, desc in _NETWORK.items()]
_COMPILED_INSTALL = [(re.compile(pat, re.IGNORECASE), pat, desc) for pat, desc in _INSTALL.items()]

_SHELL_BUILTINS: frozenset[str] = frozenset({
    "echo", "mkdir", "cd", "date", "if", "then", "else", "fi",
    "for", "do", "done", "while", "|", "&&", "||", "true",
    "false", "exit", "trap", "source", ".", "test", "[", "[[",
    "export", "set", "local", "readonly", "declare",
})


class SafetyValidator:
    """Deterministic output validator. 10 layers of checks."""

    def __init__(
        self,
        allowlist: list[str] | tuple[str, ...] | None = None,
        slurm_max_nodes: int = 4,
        slurm_max_hours: int = 72,
    ) -> None:
        self._ast = PythonASTAnalyzer()
        self._path = PathValidator()
        self._allowlist = frozenset(allowlist) if allowlist else frozenset()
        self._slurm_max_nodes = slurm_max_nodes
        self._slurm_max_hours = slurm_max_hours

    def validate(self, code: str, language: str = "bash") -> SafetyReport:
        """Run all 10 validation layers."""
        vs: list[SafetyViolation] = []
        vs.extend(self._regex_check(code, _COMPILED_BLOCKLIST, "critical"))      # L1
        vs.extend(self._regex_check(code, _COMPILED_OBFUSCATION, "critical"))    # L2
        vs.extend(self._regex_check(code, _COMPILED_NETWORK, "critical"))        # L3
        vs.extend(self._check_installs(code))                           # L4
        vs.extend(self._check_paths(code))                              # L5
        vs.extend(self._check_slurm(code))                              # L6
        vs.extend(self._check_unquoted_vars(code))                      # L7
        if language == "python":
            vs.extend(self._check_ast(code))                            # L8
        vs.extend(self._check_allowlist(code))                          # L9
        vs.extend(self._check_best_practices(code, language))           # L10

        has_critical = any(v.severity == "critical" for v in vs)
        return SafetyReport(
            passed=not has_critical,
            violations=vs,
            script_hash=hashlib.sha256(code.encode()).hexdigest(),
        )

    # --- Layer helpers ---

    @staticmethod
    def _regex_check(code: str, compiled_patterns: list[tuple[re.Pattern[str], str, str]], severity: str) -> list[SafetyViolation]:
        vs: list[SafetyViolation] = []
        for regex, pat, desc in compiled_patterns:
            for m in regex.finditer(code):
                line = code[: m.start()].count("\n") + 1
                vs.append(SafetyViolation(severity, line, desc, pat))
        return vs

    def _check_installs(self, code: str) -> list[SafetyViolation]:
        vs: list[SafetyViolation] = []
        for regex, pat, desc in _COMPILED_INSTALL:
            for m in regex.finditer(code):
                line = code[: m.start()].count("\n") + 1
                vs.append(SafetyViolation(
                    "critical", line,
                    f"{desc} in generated script. BioPipe generates logic, not env setup.",
                    pat,
                ))
        return vs

    def _check_paths(self, code: str) -> list[SafetyViolation]:
        return [
            SafetyViolation(pv.severity, None, f"Path: {pv.reason}: {pv.path}", pv.path)
            for pv in self._path.validate(code)
        ]

    def _check_slurm(self, code: str) -> list[SafetyViolation]:
        vs: list[SafetyViolation] = []
        m = re.search(r"--nodes[=\s]+(\d+)", code)
        if m and int(m.group(1)) > self._slurm_max_nodes:
            vs.append(SafetyViolation(
                "warning", code[: m.start()].count("\n") + 1,
                f"SLURM --nodes={m.group(1)} > limit {self._slurm_max_nodes}",
                f"--nodes>{self._slurm_max_nodes}",
            ))
        m = re.search(r"--time[=\s]+(\d+):(\d+):(\d+)", code)
        if m and int(m.group(1)) > self._slurm_max_hours:
            vs.append(SafetyViolation(
                "warning", code[: m.start()].count("\n") + 1,
                f"SLURM --time={m.group(1)}h > limit {self._slurm_max_hours}h",
                f"--time>{self._slurm_max_hours}h",
            ))
        return vs

    @staticmethod
    def _check_unquoted_vars(code: str) -> list[SafetyViolation]:
        vs: list[SafetyViolation] = []
        for i, line in enumerate(code.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            for m in re.finditer(r'(?<!")\$\w+(?!")', stripped):
                before = stripped[: m.start()]
                if before.count("'") % 2 == 0 and before.count('"') % 2 == 0:
                    vs.append(SafetyViolation(
                        "warning", i,
                        f'Unquoted variable {m.group()} — use "{m.group()}"',
                        "unquoted_var",
                    ))
        return vs

    def _check_ast(self, code: str) -> list[SafetyViolation]:
        return [
            SafetyViolation(av.severity, av.line, f"AST: {av.description}", av.node_type)
            for av in self._ast.analyze(code)
        ]

    def _check_allowlist(self, code: str) -> list[SafetyViolation]:
        if not self._allowlist:
            return []
        vs: list[SafetyViolation] = []
        for i, line in enumerate(code.split("\n"), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" in stripped.split()[0]:
                continue
            parts = stripped.split()
            if not parts:
                continue
            cmd = parts[0].split("/")[-1]
            if cmd.startswith("$") or cmd in _SHELL_BUILTINS or cmd in self._allowlist:
                continue
            vs.append(SafetyViolation(
                "warning", i, f"Unknown tool: {cmd}", f"not_in_allowlist:{cmd}",
            ))
        return vs

    @staticmethod
    def _check_best_practices(code: str, language: str) -> list[SafetyViolation]:
        vs: list[SafetyViolation] = []
        if language == "bash":
            if "set -euo pipefail" not in code:
                vs.append(SafetyViolation("warning", 1, "Missing set -euo pipefail", "strict_mode"))
            if not code.strip().startswith("#!/"):
                vs.append(SafetyViolation("warning", 1, "Missing shebang", "shebang"))
            if "BioPipe-CLI Generated" not in code:
                vs.append(SafetyViolation("warning", 1, "Missing metadata header", "header"))
        return vs
