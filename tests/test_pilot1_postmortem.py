"""Recompute Pilot 1 postmortem metrics from raw trajectory (offline, no API).

Tests do NOT hardcode expected loop numbers — they recompute from
pilot1_episode.json and compare against the written artifacts. If the
script, JSON artifacts, and raw data disagree, these tests fail.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EP = ROOT / "results/pilot1_live_run/pilot1_episode.json"
OUT = ROOT / "results/pilot1_postmortem"
SCRIPT = ROOT / "scripts" / "analyze_pilot1_postmortem.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pilot1_postmortem", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ep():
    assert EP.exists(), "Pilot 1 episode artifact required"
    return json.loads(EP.read_text(encoding="utf-8"))


def test_task_description_not_counted_as_object_discovery():
    """A1: goal wording containing 'book' must not mark object as discovered."""
    mod = _load_module()
    ep = _ep()
    diag = mod.goal_progress_flags(ep)
    # The raw trajectory DOES contain the phrase "look at book under the desklamp"
    # inside observation_before[0] as task description. It must not count.
    assert diag["task_description_present_in_obs"] is True
    assert diag["book_discovered_in_env_feedback"] is False
    assert diag["desklamp_discovered_in_env_feedback"] is False
    assert diag["book_location_status"] == "UNKNOWN_FROM_TRAJECTORY"
    assert diag["desklamp_location_status"] == "UNKNOWN_FROM_TRAJECTORY"
    assert diag["book_location_known_from_trajectory"] is False
    # objects list must not contain book/desklamp purely from goal text
    # (book may appear only if pure env feedback shows it — here it must not)
    assert "book" not in diag["objects_surfaced_in_env_feedback"]
    assert "desklamp" not in diag["objects_surfaced_in_env_feedback"]


def test_strip_task_description_is_selective():
    mod = _load_module()
    text = (
        "You are in the middle of a room. Looking quickly around you, you see a bed 1.\n"
        "Your task is to: look at book under the desklamp.\n"
        "On the desk 1, you see a cellphone 3."
    )
    clean = mod.strip_task_description(text)
    assert "book" not in clean.lower()
    assert "cellphone" in clean.lower()
    assert "bed 1" in clean.lower()


def test_loop_metrics_recomputed_not_hardcoded():
    """A2: recompute from raw episode; artifacts must match the recomputation."""
    mod = _load_module()
    ep = _ep()
    recomputed = mod.recompute_from_trajectory(ep["trajectory"])
    artifact = json.loads((OUT / "loop_metrics.json").read_text(encoding="utf-8"))

    # definitions clarify TYPES vs EXTRA occurrences
    assert recomputed["state_action_pair_repeat_count"] == len(
        {p for p, c in Counter(
            (str(t["observation_before"]).strip(), t["action"]) for t in ep["trajectory"]
        ).items() if c > 1}
    )
    # extra occurrences
    pair_c = Counter(
        (str(t["observation_before"]).strip(), t["action"]) for t in ep["trajectory"]
    )
    assert recomputed["state_action_loop_occurrences"] == sum(
        c - 1 for c in pair_c.values() if c > 1
    )

    # artifact must equal recomputation
    assert artifact["state_action_pair_repeat_count"] == recomputed["state_action_pair_repeat_count"]
    assert artifact["state_action_loop_occurrences"] == recomputed["state_action_loop_occurrences"]
    assert artifact["obs_change_after_action_ratio"] == pytest.approx(
        recomputed["obs_change_after_action_ratio"]
    )
    assert artifact["obs_change_denominator"] == recomputed["obs_change_denominator"]
    assert artifact["obs_change_count"] == recomputed["obs_change_count"]
    assert artifact["rslr"] == pytest.approx(recomputed["rslr"])

    # TYPES != EXTRA when any pair repeats more than twice
    if recomputed["state_action_loop_occurrences"] > recomputed["state_action_pair_repeat_count"]:
        assert recomputed["state_action_pair_repeat_count"] != recomputed["state_action_loop_occurrences"]


def test_obs_change_ratio_denominator_is_T_minus_1():
    mod = _load_module()
    ep = _ep()
    r = mod.recompute_from_trajectory(ep["trajectory"])
    T = r["T"]
    assert r["obs_change_denominator"] == T - 1
    # denominator documented
    assert "T-1" in mod.DEFS["obs_change_after_action_ratio"] or "(T-1)" in mod.DEFS["obs_change_after_action_ratio"]


def test_written_artifacts_consistent_across_files():
    mod = _load_module()
    ep = _ep()
    r = mod.recompute_from_trajectory(ep["trajectory"])
    ad = json.loads((OUT / "action_distribution.json").read_text(encoding="utf-8"))
    lm = json.loads((OUT / "loop_metrics.json").read_text(encoding="utf-8"))
    bd = json.loads((OUT / "behavioral_diagnosis.json").read_text(encoding="utf-8"))

    # action distribution still matches raw
    assert ad["action_distribution"] == dict(Counter(t["action"] for t in ep["trajectory"]))
    # loop numbers identical in the two JSON files and in recomputation
    for key in (
        "state_action_pair_repeat_count",
        "state_action_loop_occurrences",
        "obs_change_after_action_ratio",
        "action_repetition_ratio",
    ):
        if key in ad.get("consistency", {}):
            assert ad["consistency"][key] == r[key] or (
                isinstance(r[key], float) and abs(ad["consistency"][key] - r[key]) < 1e-12
            )
        assert lm[key] == r[key] or (
            isinstance(r[key], float) and abs(lm[key] - r[key]) < 1e-12
        )
        assert bd["loop_metrics_summary"][key] == r[key] or (
            isinstance(r[key], float)
            and abs(bd["loop_metrics_summary"][key] - r[key]) < 1e-12
        )


def test_action_distribution_matches_raw_trajectory():
    ep = _ep()
    dist = Counter(t["action"] for t in ep["trajectory"])
    assert dist == Counter(
        {"examine desk 1": 16, "look": 7, "go to desk 1": 3, "go to shelf 1": 3}
    )
    assert sum(dist.values()) == 29
