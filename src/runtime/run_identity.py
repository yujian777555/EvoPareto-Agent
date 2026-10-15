"""Run identity: validated git SHA + immutable run manifest (Pilot1 preflight).

Docker containers may not mount .git; the host resolves the SHA and passes
it via GIT_SHA. We require a real 40-hex commit id — never 'unknown'/'docker'
and never a hand-written constant.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN = {"unknown", "docker", "none", "null", "test", "dev", ""}


class GitIdentityError(RuntimeError):
    pass


def resolve_git_sha(*, env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None) -> str:
    """Return a validated 40-hex SHA.

    Priority: GIT_SHA env (host-verified) -> local `git rev-parse HEAD`.
    """
    source = ""
    candidate = ""
    env = os.environ if env is None else env
    raw = (env.get("GIT_SHA") or "").strip()
    if raw:
        candidate = raw
        source = "GIT_SHA"
    else:
        try:
            candidate = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                stderr=subprocess.STDOUT,
            ).decode("utf-8", errors="replace").strip()
            source = "git_rev_parse"
        except Exception as e:
            raise GitIdentityError(f"cannot resolve git SHA: {e}") from e

    if not candidate or candidate.lower() in _FORBIDDEN:
        raise GitIdentityError(f"refusing non-commit git SHA {candidate!r} (source={source})")
    if not _HEX40.match(candidate):
        raise GitIdentityError(
            f"invalid git SHA {candidate!r}: need 40 hex chars (source={source})"
        )
    return candidate


def write_run_manifest(
    path: str | Path,
    *,
    git_sha: str,
    manifest_sha256: str,
    experiment_id: str,
    model: str,
    rate_version: str,
    task_index: int,
    seed: int,
    objective_version: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist an immutable run identity record. Refuses unvalidated SHA."""
    if not _HEX40.match(str(git_sha)):
        raise GitIdentityError(f"run manifest refuses git_sha={git_sha!r}")
    payload: Dict[str, Any] = {
        "git_sha": git_sha,
        "manifest_sha256": manifest_sha256,
        "experiment_id": experiment_id,
        "model": model,
        "rate_version": rate_version,
        "task_index": int(task_index),
        "seed": int(seed),
        "objective_version": objective_version,
    }
    if extra:
        payload.update(extra)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
