"""Benchmark schema validation (fail-closed) — Phase5-R3-R2 Stage D."""

from __future__ import annotations

from typing import Any, Dict, Sequence

NATIVE_ALFWORLD_SCHEMA = {
    "required": {"gamefile", "split", "won", "score", "trajectory"},
    "kind": "real_environment",
}
PROXY_SCHEMA = {
    "required": {"task_id", "genome", "success", "steps", "tokens", "cost", "trajectory"},
    "kind": "real_llm_proxy",
}


class SchemaMismatch(RuntimeError):
    pass


def validate_episode_schema(record: Dict[str, Any], expected_kind: str) -> None:
    if expected_kind == "real_environment":
        if record.get("evaluation_kind") != "real_environment":
            raise SchemaMismatch(
                f"expected real_environment, got {record.get('evaluation_kind')}"
            )
        for k in ("success", "steps", "trajectory"):
            if k not in record:
                raise SchemaMismatch(f"missing {k}")
        # Native success must not come from capability prior fields.
        if "capability" in record or "genome_capability" in record:
            raise SchemaMismatch("capability prior must not appear in native episodes")
    elif expected_kind == "real_llm_proxy":
        for k in PROXY_SCHEMA["required"]:
            if k not in record:
                raise SchemaMismatch(f"missing {k}")
    else:
        raise SchemaMismatch(f"unknown kind {expected_kind}")


def fail_closed_cross_benchmark(
    train_tasks: Sequence[Dict[str, Any]],
    test_tasks: Sequence[Dict[str, Any]],
    *,
    expected_schema_keys: Sequence[str],
) -> None:
    """Reject mixed schemas across benchmarks (e.g. realworld catalog into ALFWorld)."""
    keys = set(expected_schema_keys)
    for t in list(train_tasks) + list(test_tasks):
        if not keys.issubset(set(t.keys())):
            raise SchemaMismatch(
                f"task keys {sorted(t.keys())} do not satisfy {sorted(keys)}"
            )
