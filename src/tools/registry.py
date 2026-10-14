"""Tool registry with call logging (Phase 5-R1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.tools.calculator import ToolResult, calculate
from src.tools.file_tool import file_list, file_read, file_write
from src.tools.search_tool import search


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    ok: bool
    output: Any

    def to_dict(self) -> dict:
        return {"name": self.name, "args": self.args, "ok": self.ok, "output": self.output}


class ToolRegistry:
    """Named tools + call log. Every invocation is recorded."""

    def __init__(self) -> None:
        self._fns: Dict[str, Callable[..., ToolResult]] = {
            "calculator": lambda **kw: calculate(kw.get("expression", "")),
            "search": lambda **kw: search(kw.get("query", ""), top_k=int(kw.get("top_k", 2))),
            "file_read": lambda **kw: file_read(kw.get("path", "")),
            "file_write": lambda **kw: file_write(kw.get("path", ""), kw.get("content", "")),
            "file_list": lambda **kw: file_list(),
        }
        self.calls: List[ToolCall] = []

    def names(self) -> List[str]:
        return sorted(self._fns)

    def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        fn = self._fns.get(name)
        if fn is None:
            result = ToolResult(name, False, None, f"unknown tool: {name}")
        else:
            try:
                result = fn(**kwargs)
            except Exception as e:  # pragma: no cover
                result = ToolResult(name, False, None, str(e))
        self.calls.append(ToolCall(name, dict(kwargs), result.ok, result.output))
        return result

    def call_log(self) -> List[dict]:
        return [c.to_dict() for c in self.calls]

    def reset(self) -> None:
        self.calls = []


def default_registry() -> ToolRegistry:
    return ToolRegistry()
