"""Recompute Pilot 1 postmortem metrics (offline, no API)."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EP = ROOT / "results/pilot1_live_run/pilot1_episode.json"
OUT = ROOT / "results/pilot1_postmortem"


def _ep():
    assert EP.exists(), "Pilot 1 episode artifact required"
    return json.loads(EP.read_text(encoding="utf-8"))


def test_action_distribution_matches_raw_trajectory():
    ep = _ep()
    dist = Counter(t["action"] for t in ep["trajectory"])
    assert dist == Counter(
        {"examine desk 1": 16, "look": 7, "go to desk 1": 3, "go to shelf 1": 3}
    )
    assert sum(dist.values()) == 29


def test_loop_metrics_reproducible():
    ep = _ep()
    traj = ep["trajectory"]
    n = len(traj)
    # RSLR definition from AGENT_BEHAVIOR_DIAGNOSTIC_PROPOSAL.md
    pairs = Counter(
        (t["observation_before"], t["action"]) for t in traj
    )
    loop_occ = sum(c - 1 for c in pairs.values() if c > 1)
    rslr = loop_occ / n
    assert loop_occ == 21
    assert abs(rslr - 21 / 29) < 1e-9
    # max consecutive same observation_after
    max_run = cur = 0
    prev = None
    for t in traj:
        o = t["observation_after"]
        cur = cur + 1 if o == prev else 1
        prev = o
        max_run = max(max_run, cur)
    assert max_run == 4
    # no-new-info ratio
    same = sum(1 for t in traj if t["observation_before"] == t["observation_after"])
    assert same == 8


def test_written_artifacts_consistent():
    for name in (
        "action_distribution.json",
        "loop_metrics.json",
        "behavioral_diagnosis.json",
        "genome_phenotype_matrix.json",
        "feasibility_budget_estimate.json",
    ):
        p = OUT / name
        assert p.exists(), name
        json.loads(p.read_text(encoding="utf-8"))
    ad = json.loads((OUT / "action_distribution.json").read_text(encoding="utf-8"))
    assert ad["matches_planner_observation"] is True
    gm = json.loads((OUT / "genome_phenotype_matrix.json").read_text(encoding="utf-8"))
    levels = {g["gene"]: g["evidence_level"] for g in gm["genes"]}
    assert levels["tool_policy"].startswith("CODE_CONFIRMED")
    assert levels["planner_strategy"] == "PROMPT_ONLY"


def test_budget_meter_formula():
    # mirror BudgetMeter.from_reasoning_budget(64, horizon=30)
    budget, horizon = 64, 30
    steps = max(1, int(round(horizon * (0.5 + budget / 128.0))))
    tokens = max(64, budget * 12)
    assert steps == 30
    assert tokens == 768
    # 29 env actions + 1 reflection charge = 30
    ep = _ep()
    assert ep["steps"] == 29
    assert ep["llm_call_count"] == 30
    assert ep["reflection_count"] == 1
