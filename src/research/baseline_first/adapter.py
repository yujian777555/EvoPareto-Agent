"""Baseline adapter interface + trace audit helpers (skeleton only)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BaselineSpec:
    name: str
    paper_id: str
    code_url: str
    version: str = "UNPINNED"
    license: str = "UNKNOWN"
    repro_status: str = "NOT_EXECUTED"


@dataclass
class TraceRecord:
    trace_id: str
    task_id: str
    actions: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    success: bool = False
    source: str = "UNKNOWN"


def load_trace_json(path: str | Path) -> TraceRecord:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return TraceRecord(
        trace_id=str(d.get("trace_id", "")),
        task_id=str(d.get("task_id", "")),
        actions=list(d.get("actions") or []),
        observations=list(d.get("observations") or []),
        success=bool(d.get("success", False)),
        source=str(d.get("source", "UNKNOWN")),
    )


def audit_trace(tr: TraceRecord) -> Dict[str, Any]:
    """Read-only trace audit: sizes, action uniqueness, loop rate."""
    n = len(tr.actions)
    uniq = len(set(tr.actions))
    pair_c = {}
    for i, a in enumerate(tr.actions):
        key = (tr.observations[i][:80] if i < len(tr.observations) else "", a)
        pair_c[key] = pair_c.get(key, 0) + 1
    loops = sum(c - 1 for c in pair_c.values() if c > 1)
    return {
        "trace_id": tr.trace_id,
        "n_steps": n,
        "unique_actions": uniq,
        "repetition_ratio": (1 - uniq / n) if n else 0.0,
        "loop_occurrences": loops,
        "success": tr.success,
        "source": tr.source,
        "evidence_level": "REPLAYED_REAL_TRACE_ANALYSIS" if tr.source == "REAL" else "SYNTHETIC",
    }


def environment_check() -> Dict[str, str]:
    import shutil
    import sys

    return {
        "python": sys.version.split()[0],
        "docker": "AVAILABLE" if shutil.which("docker") else "MISSING",
        "curl": "AVAILABLE" if shutil.which("curl") or shutil.which("curl.exe") else "MISSING",
        "live_real_model_evaluation": "NOT_EXECUTED",
    }
