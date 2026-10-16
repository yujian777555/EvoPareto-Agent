"""Pilot 1 behavioral postmortem — recomputable metrics from raw trajectory.

All loop/stagnation metrics have explicit mathematical definitions.
No real API calls. Reads only preserved Pilot 1 artifacts.

Object-discovery rule:
  Task-description text ("Your task is to: ...") is NEVER counted as evidence
  that the agent observed the target object in the environment. Only pure
  environment feedback (observation text with task-description lines removed)
  can surface an object.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
EP_PATH = ROOT / "results/pilot1_live_run/pilot1_episode.json"
OUT = ROOT / "results/pilot1_postmortem"

# ------------------------------------------------------------------ #
# Metric definitions (single source of truth)
# ------------------------------------------------------------------ #
DEFS = {
    "state_definition": (
        "state at step t := observation_before[t] (the environment text the "
        "agent saw when it chose action[t]), string-equal after .strip()"
    ),
    "action_repetition_ratio": (
        "1 - |unique actions| / T ; T = number of environment actions"
    ),
    "max_consecutive_same_action": (
        "max run-length of identical consecutive actions"
    ),
    "max_consecutive_same_observation": (
        "max run-length of identical observation_after strings"
    ),
    "state_action_pair_repeat_count": (
        "NUMBER OF DISTINCT (state, action) pairs whose occurrence count >= 2. "
        "This is a count of pair TYPES, not of extra occurrences."
    ),
    "state_action_loop_occurrences": (
        "EXTRA occurrences beyond the first of every repeated (state, action) "
        "pair = sum_{p: count(p)>1} (count(p) - 1). "
        "This is an occurrence count, not a type count."
    ),
    "no_new_info_action_ratio": (
        "fraction of steps t where observation_after[t] == observation_before[t] "
        "(denominator T)"
    ),
    "obs_change_after_action_ratio": (
        "fraction of consecutive comparison slots where "
        "observation_after[t] != observation_after[t-1]. "
        "Denominator is T-1 (pairs of consecutive steps), numerator is the "
        "number of those pairs that differ. Undefined for T<2."
    ),
    "rslr_repeated_state_action_loop_rate": (
        "state_action_loop_occurrences / T"
    ),
    "unique_location_visit_count": (
        "number of distinct ALFWorld location tokens seen in environment "
        "feedback or targeted by 'go to' actions"
    ),
    "half_behavior_divergence": (
        "1 - Jaccard(action SET of first half, action SET of second half); "
        "0 = identical action sets"
    ),
}

TASK_DESC_RE = re.compile(
    r"^\s*your task is to:.*$", re.I | re.M
)


def strip_task_description(text: str) -> str:
    """Remove task-description lines so goal wording is not object evidence."""
    return TASK_DESC_RE.sub("", text or "")


def env_object_terms(text: str) -> List[str]:
    """Object terms appearing in PURE environment feedback only."""
    clean = strip_task_description(text).lower()
    return re.findall(
        r"\b(?:book|desklamp|desk lamp|cellphone|keychain|laptop|pen|"
        r"shelf|desk|drawer|safe|garbagecan|sidetable|bed|lamp)\b",
        clean,
    )


def _loc_tokens(text: str) -> List[str]:
    return re.findall(
        r"\b(?:desk|shelf|bed|drawer|garbagecan|safe|sidetable|table|counter|stove|sink|toilet|bathtub|mirror)\s+\d+\b",
        text or "",
        flags=re.I,
    )


def recompute_from_trajectory(trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Single function that computes every loop metric from raw steps."""
    n = len(trajectory)
    actions = [str(t.get("action") or "") for t in trajectory]
    obs_before = [str(t.get("observation_before") or "").strip() for t in trajectory]
    obs_after = [str(t.get("observation_after") or "").strip() for t in trajectory]

    dist = Counter(actions)
    unique_actions = sorted(dist)
    rep_ratio = 1.0 - (len(unique_actions) / n) if n else 0.0

    # max consecutive same action
    max_run_a = cur = 0
    prev = None
    for a in actions:
        cur = cur + 1 if a == prev else 1
        prev = a
        max_run_a = max(max_run_a, cur)

    # max consecutive same observation_after
    max_run_o = cur = 0
    prev = None
    for o in obs_after:
        cur = cur + 1 if o == prev else 1
        prev = o
        max_run_o = max(max_run_o, cur)

    # state = observation_before[t]
    pair_counter: Counter = Counter(zip(obs_before, actions))
    repeated_pairs = {p: c for p, c in pair_counter.items() if c > 1}
    pair_repeat_count = len(repeated_pairs)          # TYPES with count>=2
    loop_occurrences = sum(c - 1 for c in repeated_pairs.values())  # EXTRA occurrences

    # no-new-info: obs_after == obs_before, denominator T
    no_new = sum(1 for t in range(n) if obs_after[t] == obs_before[t])
    no_new_ratio = no_new / n if n else 0.0

    # obs change between consecutive observation_after, denominator T-1
    if n > 1:
        obs_changed = sum(1 for t in range(1, n) if obs_after[t] != obs_after[t - 1])
        obs_change_ratio = obs_changed / (n - 1)
        obs_change_denominator = n - 1
    else:
        obs_changed = 0
        obs_change_ratio = 0.0
        obs_change_denominator = 0

    rslr = loop_occurrences / n if n else 0.0

    return {
        "T": n,
        "action_distribution": dict(dist),
        "unique_action_count": len(unique_actions),
        "unique_actions": unique_actions,
        "action_repetition_ratio": rep_ratio,
        "max_consecutive_same_action": max_run_a,
        "max_consecutive_same_observation": max_run_o,
        "state_action_pair_repeat_count": pair_repeat_count,
        "state_action_loop_occurrences": loop_occurrences,
        "rslr": rslr,
        "no_new_info_action_count": no_new,
        "no_new_info_action_ratio": no_new_ratio,
        "obs_change_count": obs_changed,
        "obs_change_denominator": obs_change_denominator,
        "obs_change_after_action_ratio": obs_change_ratio,
        "repeated_pair_details": [
            {"action": k[1], "observation_before_preview": k[0][:80], "count": v}
            for k, v in sorted(repeated_pairs.items(), key=lambda x: -x[1])
        ],
    }


def analyze(ep: Dict[str, Any]) -> Dict[str, Any]:
    traj = ep.get("trajectory") or []
    m = recompute_from_trajectory(traj)
    n = m["T"]
    actions = [str(t.get("action") or "") for t in traj]
    obs_after = [str(t.get("observation_after") or "") for t in traj]

    # locations from pure env feedback + go-to actions
    locs: List[str] = []
    for o in obs_after:
        locs.extend(_loc_tokens(strip_task_description(o)))
    for a in actions:
        mm = re.match(r"go to (.+)", a)
        if mm:
            locs.append(mm.group(1).strip())
    unique_locs = sorted(set(locs))

    h = n // 2
    first = set(actions[:h])
    second = set(actions[h:])
    half_div = 1.0 - (len(first & second) / len(first | second)) if (first or second) else 0.0

    return {
        **m,
        "unique_location_tokens": unique_locs,
        "unique_location_visit_count": len(unique_locs),
        "half_behavior_divergence": half_div,
        "first_half_size": h,
        "second_half_size": n - h,
        "first_half_action_dist": dict(Counter(actions[:h])),
        "second_half_action_dist": dict(Counter(actions[h:])),
        "metric_definitions": DEFS,
    }


def goal_progress_flags(ep: Dict[str, Any]) -> Dict[str, Any]:
    """Object discovery from PURE environment feedback only.

    Task-description text is explicitly excluded.
    """
    traj = ep.get("trajectory") or []
    goal = str(ep.get("goal") or "")

    # pure env feedback = observation text minus task-description lines
    pure_env_parts: List[str] = []
    task_desc_seen = False
    for t in traj:
        for key in ("observation_before", "observation_after"):
            raw = str(t.get(key) or "")
            if re.search(r"your task is to:", raw, re.I):
                task_desc_seen = True
            pure_env_parts.append(strip_task_description(raw))
    pure_env = "\n".join(pure_env_parts).lower()
    actions = [str(t.get("action") or "").lower() for t in traj]

    # Object discovery: terms in PURE env feedback only
    book_in_env = bool(re.search(r"\bbook\b", pure_env))
    desklamp_in_env = bool(re.search(r"desklamp|desk lamp|desk-lamp", pure_env))
    lamp_in_env = bool(re.search(r"\blamp\b", pure_env))

    opened_container = any(a.startswith("open ") for a in actions)
    took_item = any(a.startswith(("take ", "pick up")) for a in actions)
    used_light = any("lamp" in a or "light" in a or a.startswith("use ") for a in actions)
    searched_book_cmd = any("book" in a for a in actions)

    env_objs = sorted(set(env_object_terms("\n".join(str(t.get("observation_before") or "") for t in traj)
                                           + "\n" + "\n".join(str(t.get("observation_after") or "") for t in traj))))

    return {
        "goal": goal,
        "won": ep.get("success"),
        "task_description_present_in_obs": task_desc_seen,
        "object_discovery_rule": (
            "task-description lines ('Your task is to: ...') are stripped before "
            "any object-discovery test; keyword presence in the goal wording is "
            "NOT evidence of seeing the object"
        ),
        "book_discovered_in_env_feedback": book_in_env,
        "desklamp_discovered_in_env_feedback": desklamp_in_env or lamp_in_env,
        "any_open_container_action": opened_container,
        "any_take_or_pick_action": took_item,
        "any_use_light_action": used_light,
        "any_action_text_contains_book": searched_book_cmd,
        "objects_surfaced_in_env_feedback": env_objs,
        "book_location_status": "seen_in_env_feedback" if book_in_env else "UNKNOWN_FROM_TRAJECTORY",
        "desklamp_location_status": (
            "seen_in_env_feedback" if (desklamp_in_env or lamp_in_env) else "UNKNOWN_FROM_TRAJECTORY"
        ),
        "book_location_known_from_trajectory": book_in_env,
        "agent_acted_on_goal_terms": searched_book_cmd or used_light,
        "looped_around_desk_shelf": True,
        "note": (
            "Do not infer object position from failure. "
            "UNKNOWN_FROM_TRAJECTORY means no environment feedback (excluding "
            "task-description text) ever surfaced the object."
        ),
    }


def budget_decode(reasoning_budget: int, horizon: int) -> Dict[str, Any]:
    steps = max(1, int(round(horizon * (0.5 + reasoning_budget / 128.0))))
    tokens = max(64, reasoning_budget * 12)
    return {
        "reasoning_budget": reasoning_budget,
        "horizon": horizon,
        "max_steps_formula": "max(1, round(horizon * (0.5 + reasoning_budget/128)))",
        "max_tokens_formula": "max(64, reasoning_budget * 12)",
        "max_steps": steps,
        "max_tokens": tokens,
    }


def genome_phenotype_matrix() -> List[Dict[str, Any]]:
    return [
        {
            "gene": "planner_strategy",
            "changes_prompt": True,
            "changes_execution": False,
            "measurable_behavior_delta": "prompt-only for native path",
            "evidence_level": "PROMPT_ONLY",
            "source": "src/runtime/interactive_agent.py select_action prompt_lines",
        },
        {
            "gene": "memory_strategy",
            "changes_prompt": True,
            "changes_execution": True,
            "measurable_behavior_delta": "short_term=1 obs line; episodic/semantic/hybrid<=3; none=0",
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/behavioral_agent.py MemoryStore",
        },
        {
            "gene": "reflection_strategy",
            "changes_prompt": True,
            "changes_execution": True,
            "measurable_behavior_delta": "none vs retry-on-parse-fail; 4 names share one path",
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/interactive_agent.py reflection block",
        },
        {
            "gene": "tool_policy",
            "changes_prompt": True,
            "changes_execution": False,
            "measurable_behavior_delta": "no-op on native ALFWorld path",
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/interactive_agent.py (self.allow unused)",
        },
        {
            "gene": "reasoning_budget",
            "changes_prompt": True,
            "changes_execution": True,
            "measurable_behavior_delta": "max steps/tokens -> cost & truncation, not step quality",
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/behavioral_agent.py BudgetMeter",
        },
    ]


def feasibility_budget(pilot_cost=0.0026718):
    per_ep = pilot_cost
    n_ep = 18  # Stage 1 approved scale
    return {
        "design": "3 tasks x 3 genomes x 2 seeds = 18 episodes",
        "per_episode_median": {"http": 30, "cost_usd": per_ep},
        "totals_18_episodes": {
            "median_http": 540,
            "median_cost_usd": round(per_ep * n_ep, 6),
        },
        "approved_caps": {"episodes": 18, "physical_http": 650, "estimated_cost_usd": 0.11},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ep = json.loads(EP_PATH.read_text(encoding="utf-8"))
    metrics = analyze(ep)
    diag = goal_progress_flags(ep)

    # cross-check block: recomputed values that tests will re-derive
    consistency = {
        "source_episode": str(EP_PATH),
        "T": metrics["T"],
        "state_action_pair_repeat_count": metrics["state_action_pair_repeat_count"],
        "state_action_loop_occurrences": metrics["state_action_loop_occurrences"],
        "obs_change_after_action_ratio": metrics["obs_change_after_action_ratio"],
        "obs_change_count": metrics["obs_change_count"],
        "obs_change_denominator": metrics["obs_change_denominator"],
        "action_repetition_ratio": metrics["action_repetition_ratio"],
        "rslr": metrics["rslr"],
    }

    (OUT / "action_distribution.json").write_text(
        json.dumps(
            {
                "action_distribution": metrics["action_distribution"],
                "unique_action_count": metrics["unique_action_count"],
                "unique_actions": metrics["unique_actions"],
                "action_repetition_ratio": metrics["action_repetition_ratio"],
                "max_consecutive_same_action": metrics["max_consecutive_same_action"],
                "half_behavior_divergence": metrics["half_behavior_divergence"],
                "first_half_action_dist": metrics["first_half_action_dist"],
                "second_half_action_dist": metrics["second_half_action_dist"],
                "first_half_size": metrics["first_half_size"],
                "second_half_size": metrics["second_half_size"],
                "steps": metrics["T"],
                "consistency": consistency,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "loop_metrics.json").write_text(
        json.dumps(
            {
                "metric_definitions": DEFS,
                "state_definition": DEFS["state_definition"],
                "max_consecutive_same_action": metrics["max_consecutive_same_action"],
                "max_consecutive_same_observation": metrics["max_consecutive_same_observation"],
                "state_action_pair_repeat_count": metrics["state_action_pair_repeat_count"],
                "state_action_loop_occurrences": metrics["state_action_loop_occurrences"],
                "rslr": metrics["rslr"],
                "repeated_pair_details": metrics["repeated_pair_details"],
                "no_new_info_action_count": metrics["no_new_info_action_count"],
                "no_new_info_action_ratio": metrics["no_new_info_action_ratio"],
                "obs_change_count": metrics["obs_change_count"],
                "obs_change_denominator": metrics["obs_change_denominator"],
                "obs_change_after_action_ratio": metrics["obs_change_after_action_ratio"],
                "unique_location_visit_count": metrics["unique_location_visit_count"],
                "unique_location_tokens": metrics["unique_location_tokens"],
                "action_repetition_ratio": metrics["action_repetition_ratio"],
                "consistency": consistency,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "behavioral_diagnosis.json").write_text(
        json.dumps(
            {
                "goal_progress": diag,
                "budget_decode": budget_decode(
                    int((ep.get("genome") or {}).get("reasoning_budget", 64)), 30
                ),
                "observation_evidence": {
                    "raw_llm_response_available": False,
                    "parse_ok_available": False,
                    "used_fallback_available": False,
                    "per_step_tokens_available": False,
                    "not_observable_from_pilot1": [
                        "raw_llm_response",
                        "parse_ok",
                        "parse_failure_reason",
                        "used_fallback",
                        "per_step_tokens",
                        "per_step_cost",
                        "reflection_trigger_step",
                    ],
                },
                "call_accounting": {
                    "env_actions": metrics["T"],
                    "llm_call_count": ep.get("llm_call_count"),
                    "reflection_count": ep.get("reflection_count"),
                },
                "loop_metrics_summary": {
                    "action_repetition_ratio": metrics["action_repetition_ratio"],
                    "max_consecutive_same_observation": metrics["max_consecutive_same_observation"],
                    "state_action_pair_repeat_count": metrics["state_action_pair_repeat_count"],
                    "state_action_loop_occurrences": metrics["state_action_loop_occurrences"],
                    "rslr": metrics["rslr"],
                    "no_new_info_action_ratio": metrics["no_new_info_action_ratio"],
                    "obs_change_after_action_ratio": metrics["obs_change_after_action_ratio"],
                },
                "consistency": consistency,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "genome_phenotype_matrix.json").write_text(
        json.dumps({"genes": genome_phenotype_matrix(), "pilot1_genome": ep.get("genome")}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "feasibility_budget_estimate.json").write_text(
        json.dumps(feasibility_budget(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("pair_repeat_count(TYPES)", metrics["state_action_pair_repeat_count"])
    print("loop_occurrences(EXTRA)", metrics["state_action_loop_occurrences"])
    print("obs_change_ratio", metrics["obs_change_after_action_ratio"],
          f"({metrics['obs_change_count']}/{metrics['obs_change_denominator']})")
    print("book_location_status", diag["book_location_status"])
    print("book_discovered_in_env_feedback", diag["book_discovered_in_env_feedback"])
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
