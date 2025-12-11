"""Static code analyzer using AST heuristics."""
from __future__ import annotations

import ast
from typing import Any, Dict, List

from sentinel.agent_core.base import Tool


_RISKY_CALLS = {"exec", "eval", "open", "__import__"}
_RISKY_MODULES = {"os", "subprocess", "pathlib", "shutil"}


def _collect_risks(tree: ast.AST) -> List[str]:
    risks: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.split(".")[0] in _RISKY_MODULES:
                    risks.append(f"Import of risky module '{alias.name}'")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _RISKY_CALLS:
                risks.append(f"Call to {func.id}")
            if isinstance(func, ast.Attribute) and func.attr in _RISKY_CALLS:
                risks.append(f"Attribute call to {func.attr}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            risks.append("Access to dunder attribute")
    return risks


def _complexity(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.BoolOp)):
            count += 1
    return count


class CodeAnalyzerTool(Tool):
    def __init__(self) -> None:
        super().__init__("code_analyzer", "Analyze Python code for safety and complexity")

    def execute(self, code: str, filename: str | None = None) -> Dict[str, Any]:
        tree = ast.parse(code, filename or "<analyzed>")
        risks = _collect_risks(tree)
        complexity = _complexity(tree)
        score = max(0, 100 - (len(risks) * 15 + complexity * 2))
        suggestions: List[str] = []
        if risks:
            suggestions.append("Remove or guard risky calls and imports")
        if complexity > 10:
            suggestions.append("Refactor to reduce branching complexity")
        if not suggestions:
            suggestions.append("Code appears safe under heuristic checks")
        return {"score": score, "risks": risks, "suggestions": suggestions}


CODE_ANALYZER_TOOL = CodeAnalyzerTool()
