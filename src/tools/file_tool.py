"""Mock file tool (Phase 5-R1). In-memory file operations, fully logged."""

from __future__ import annotations

from typing import Dict

from src.tools.calculator import ToolResult

_FILES: Dict[str, str] = {
    "notes.txt": "meeting notes\n- ship PEEM-PPEC\n- freeze experiments\n",
    "data.csv": "id,value\n1,10\n2,20\n3,30\n",
    "todo.md": "- [ ] write paper\n- [ ] submit CCF-B\n",
}


def file_read(path: str) -> ToolResult:
    key = (path or "").strip()
    if key not in _FILES:
        return ToolResult("file_read", False, None, f"not found: {key}")
    return ToolResult("file_read", True, _FILES[key])


def file_write(path: str, content: str) -> ToolResult:
    key = (path or "").strip()
    if not key:
        return ToolResult("file_write", False, None, "empty path")
    _FILES[key] = str(content)
    return ToolResult("file_write", True, {"path": key, "bytes": len(content)})


def file_list() -> ToolResult:
    return ToolResult("file_list", True, sorted(_FILES.keys()))
