"""Evaluation cache (Phase 4-R1).

Evolutionary search re-evaluates identical genomes. Cache key = genome hash
(+ task_id / benchmark / seed) so repeated API calls are skipped.

Stored per entry:
    genome_id, task_id, objective_vector, tokens, cost, latency
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome


def genome_hash(genome: AgentGenome) -> str:
    """Stable short hash of a genome configuration."""
    payload = json.dumps(genome.to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def make_key(
    genome: AgentGenome,
    *,
    task_id: str,
    benchmark: str = "",
    seed: int = 0,
    backend: str = "",
    model: str = "",
    preference: str = "",
) -> str:
    """Cache key must isolate every evaluation context (Phase5-Audit).

    Components: genome | benchmark | task_id | seed | backend | model | preference.
    """
    g = genome_hash(genome)
    raw = "|".join([
        g,
        str(benchmark),
        str(task_id),
        str(seed),
        str(backend),
        str(model),
        str(preference),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class CacheEntry:
    genome_id: str
    task_id: str
    objective_vector: List[float]
    tokens: int = 0
    cost: float = 0.0
    latency: float = 0.0
    success: bool = False
    steps: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        return cls(
            genome_id=str(data["genome_id"]),
            task_id=str(data["task_id"]),
            objective_vector=[float(x) for x in data["objective_vector"]],
            tokens=int(data.get("tokens", 0)),
            cost=float(data.get("cost", 0.0)),
            latency=float(data.get("latency", 0.0)),
            success=bool(data.get("success", False)),
            steps=int(data.get("steps", 0)),
            extra=dict(data.get("extra", {})),
        )


class EvaluationCache:
    """In-memory + optional JSON-persistent evaluation cache."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else None
        self._store: Dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0
        self.saved_tokens = 0
        self.saved_cost = 0.0
        if self.path and self.path.exists():
            self.load_json(self.path)

    def __len__(self) -> int:
        return len(self._store)

    def get(self, key: str) -> Optional[CacheEntry]:
        e = self._store.get(key)
        if e is not None:
            self.hits += 1
            self.saved_tokens += e.tokens
            self.saved_cost += e.cost
        else:
            self.misses += 1
        return e

    def put(self, key: str, entry: CacheEntry) -> None:
        self._store[key] = entry

    def lookup_genome_task(
        self,
        genome: AgentGenome,
        task_id: str,
        *,
        benchmark: str = "",
        seed: int = 0,
        backend: str = "",
        model: str = "",
        preference: str = "",
    ) -> Optional[CacheEntry]:
        return self.get(make_key(
            genome, task_id=task_id, benchmark=benchmark, seed=seed,
            backend=backend, model=model, preference=preference,
        ))

    def store_genome_task(
        self,
        genome: AgentGenome,
        task_id: str,
        entry: CacheEntry,
        *,
        benchmark: str = "",
        seed: int = 0,
        backend: str = "",
        model: str = "",
        preference: str = "",
    ) -> None:
        key = make_key(
            genome, task_id=task_id, benchmark=benchmark, seed=seed,
            backend=backend, model=model, preference=preference,
        )
        if not entry.genome_id:
            entry.genome_id = genome_hash(genome)
        self.put(key, entry)

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "n_entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": (self.hits / total) if total else 0.0,
            "saved_tokens": self.saved_tokens,
            "saved_cost": self.saved_cost,
        }

    # ------------------------------------------------------------------ #
    def save_json(self, path: Optional[str | Path] = None) -> None:
        p = Path(path or self.path or "cache.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": {k: v.to_dict() for k, v in self._store.items()},
            "stats": self.stats(),
        }
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.path = p

    def load_json(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for k, v in dict(data.get("entries", {})).items():
            self._store[k] = CacheEntry.from_dict(v)
