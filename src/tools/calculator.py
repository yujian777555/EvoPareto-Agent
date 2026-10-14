"""Calculator tool (Phase 5-R1). Safe arithmetic evaluation."""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@dataclass
class ToolResult:
    tool: str
    ok: bool
    output: Any
    error: str = ""

    def to_dict(self) -> dict:
        return {"tool": self.tool, "ok": self.ok, "output": self.output, "error": self.error}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def calculate(expression: str) -> ToolResult:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        value = _eval_node(tree)
        return ToolResult("calculator", True, value)
    except Exception as e:
        return ToolResult("calculator", False, None, str(e))
