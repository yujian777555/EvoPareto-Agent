"""Mock search tool (Phase 5-R1). Deterministic offline search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from src.tools.calculator import ToolResult

_CORPUS: Dict[str, List[str]] = {
    "climate": [
        "Global temperatures have risen ~1.1C since pre-industrial times.",
        "IPCC reports emphasize mitigation and adaptation pathways.",
    ],
    "python": [
        "Python 3.12 improves error messages and perf for comprehensions.",
        "Typing hints and dataclasses are widely used in modern Python.",
    ],
    "renewable": [
        "Solar PV capacity has grown rapidly over the last decade.",
        "Grid-scale battery storage is becoming cheaper.",
    ],
    "default": [
        "Mock search result 1 for the query.",
        "Mock search result 2 with generic information.",
    ],
}


def search(query: str, *, top_k: int = 2) -> ToolResult:
    q = (query or "").lower().strip()
    if not q:
        return ToolResult("search", False, [], "empty query")
    hits = None
    for key, docs in _CORPUS.items():
        if key != "default" and key in q:
            hits = docs
            break
    if hits is None:
        hits = _CORPUS["default"]
    return ToolResult("search", True, hits[: max(1, top_k)])
