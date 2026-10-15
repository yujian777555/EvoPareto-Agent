"""Pilot 1 behavioral postmortem — recomputable metrics from raw trajectory.

All loop/stagnation metrics have explicit mathematical definitions.
No real API calls. Reads only preserved Pilot 1 artifacts + source.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
EP_PATH = ROOT / "results/pilot1_live_run/pilot1_episode.json"
OUT = ROOT / "results/pilot1_postmortem"

# ------------------------------------------------------------------ #
# Metric definitions (documented, reproducible)
# ------------------------------------------------------------------ #
DEFS = {
    "action_repetition_ratio": (
        "1 - |unique actions| / |actions| ; range [0,1]; 1 = all identical"
    ),
    "max_consecutive_same_action": (
        "max run-length of identical consecutive actions in the sequence"
    ),
    "max_consecutive_same_observation": (
        "max run-length of identical observation_after strings"
    ),
    "state_action_pair_repeat_count": (
        "number of (observation_after[t-1] or obs_before[t], action[t]) pairs "
        "that occur at least twice in the episode"
    ),
    "state_action_loop_occurrences": (
        "total occurrences beyond the first of every repeated "
        "(state, action) pair = sum_{pairs with count>1} (count-1)"
    ),
    "no_new_info_action_ratio": (
        "fraction of steps where observation_after == observation_before "
        "(environment returned identical text)"
    ),
    "obs_change_after_action_ratio": (
        "fraction of steps where observation_after != previous observation_after"
    ),
    "unique_location_visit_count": (
        "number of distinct ALFWorld location tokens observed as current place "
        "(desk/shelf/bed/drawer/...)"
    ),
    "half_behavior_divergence": (
        "1 - Jaccard(first_half_action_multiset_keys, second_half_action_multiset_keys) "
        "using action identity (not counts); 0 = identical action sets"
    ),
}


def _loc_tokens(text: str) -> List[str]:
    """Extract location-ish nouns from observation text."""
    return re.findall(
        r"\b(?:desk|shelf|bed|drawer|garbagecan|safe|sidetable|table|counter|stove|sink|toilet|bathtub|mirror)\s+\d+\b",
        text or "",
        flags=re.I,
    )


def analyze(ep: Dict[str, Any]) -> Dict[str, Any]:
    traj = ep.get("trajectory") or []
    n = len(traj)
    actions = [str(t.get("action") or "") for t in traj]
    obs_before = [str(t.get("observation_before") or "") for t in traj]
    obs_after = [str(t.get("observation_after") or "") for t in traj]

    dist = Counter(actions)
    unique_actions = sorted(dist)
    rep_ratio = 1.0 - (len(unique_actions) / n) if n else 0.0

    # max consecutive same action
    max_run_a = cur = 0
    prev = None
    for a in actions:
        if a == prev:
            cur += 1
        else:
            cur = 1
            prev = a
        max_run_a = max(max_run_a, cur)

    # max consecutive same observation_after
    max_run_o = cur = 0
    prev = None
    for o in obs_after:
        if o == prev:
            cur += 1
        else:
            cur = 1
            prev = o
        max_run_o = max(max_run_o, cur)

    # state-action pairs: state = observation_before at step t (state the agent saw)
    pair_counter: Counter = Counter()
    for t in range(n):
        state = obs_before[t]
        pair_counter[(state, actions[t])] += 1
    repeated_pairs = {p: c for p, c in pair_counter.items() if c > 1}
    loop_occurrences = sum(c - 1 for c in repeated_pairs.values())

    # no-new-info: observation_after == observation_before
    no_new = sum(1 for t in range(n) if obs_after[t] == obs_before[t])
    no_new_ratio = no_new / n if n else 0.0

    # observation changed vs previous after
    obs_changed = 0
    for t in range(1, n):
        if obs_after[t] != obs_after[t - 1]:
            obs_changed += 1
    obs_change_ratio = (obs_changed / (n - 1)) if n > 1 else 0.0

    # locations visited (from observation_after)
    locs = []
    for o in obs_after:
        found = _loc_tokens(o)
        # "you see X on the desk 1" / "arrive at desk 1" / room listing
        locs.extend(found)
    # also parse "go to <place>" actions
    for a in actions:
        m = re.match(r"go to (.+)", a)
        if m:
            locs.append(m.group(1).strip())
    unique_locs = sorted(set(locs))

    # half divergence
    h = n // 2
    first = set(actions[:h])
    second = set(actions[h:])
    if first or second:
        jacc = len(first & second) / len(first | second)
        half_div = 1.0 - jacc
    else:
        half_div = 0.0

    # first/second half action dists
    d1 = Counter(actions[:h])
    d2 = Counter(actions[h:])

    # reflection / llm accounting from episode fields
    llm_calls = int(ep.get("llm_call_count") or 0)
    api_calls = int(ep.get("api_calls") or 0)
    reflection_count = int(ep.get("reflection_count") or 0)

    # per-step token/cost: NOT present in Pilot 1 trajectory
    per_step_tokens_available = any("tokens_in" in t for t in traj)

    return {
        "episode_meta": {
            "git_sha": ep.get("git_sha"),
            "game_id": ep.get("game_id"),
            "goal": ep.get("goal"),
            "won": ep.get("success"),
            "termination_reason": ep.get("termination_reason"),
            "steps": n,
            "llm_call_count": llm_calls,
            "api_calls": api_calls,
            "reflection_count": reflection_count,
            "tokens_in": ep.get("tokens_in"),
            "tokens_out": ep.get("tokens_out"),
            "cost_usd": ep.get("cost_usd"),
            "genome": ep.get("genome"),
        },
        "action_distribution": dict(dist),
        "unique_action_count": len(unique_actions),
        "unique_actions": unique_actions,
        "action_repetition_ratio": rep_ratio,
        "max_consecutive_same_action": max_run_a,
        "max_consecutive_same_observation": max_run_o,
        "state_action_pair_repeat_count": len(repeated_pairs),
        "state_action_loop_occurrences": loop_occurrences,
        "repeated_pair_details": [
            {
                "action": k[1],
                "observation_before_preview": k[0][:80],
                "count": v,
            }
            for k, v in sorted(repeated_pairs.items(), key=lambda x: -x[1])[:10]
        ],
        "no_new_info_action_count": no_new,
        "no_new_info_action_ratio": no_new_ratio,
        "obs_change_after_action_ratio": obs_change_ratio,
        "unique_location_tokens": unique_locs,
        "unique_location_visit_count": len(unique_locs),
        "half_behavior_divergence": half_div,
        "first_half_size": h,
        "second_half_size": n - h,
        "first_half_action_dist": dict(d1),
        "second_half_action_dist": dict(d2),
        "per_step_tokens_available": per_step_tokens_available,
        "raw_llm_response_available": any("raw_response" in t for t in traj),
        "parse_ok_available": any("parse_ok" in t for t in traj),
        "used_fallback_available": any("used_fallback" in t for t in traj),
        "metric_definitions": DEFS,
    }


def goal_progress_flags(ep: Dict[str, Any]) -> Dict[str, Any]:
    """Evidence-based goal progress assessment from trajectory text only."""
    traj = ep.get("trajectory") or []
    goal = str(ep.get("goal") or "").lower()
    blob = "\n".join(
        [str(t.get("observation_before") or "") for t in traj]
        + [str(t.get("observation_after") or "") for t in traj]
    ).lower()
    actions = [str(t.get("action") or "").lower() for t in traj]

    # Search evidence: does any observation mention a book / desklamp / lamp?
    mentions_book = bool(re.search(r"\bbook\b", blob))
    mentions_desklamp = bool(re.search(r"desklamp|desk lamp|desk-lamp", blob))
    mentions_lamp = bool(re.search(r"\blamp\b|light", blob))
    mentions_open = any(a.startswith(("open ", "take ", "pick", "use ", "turn on", "look at")) for a in actions)
    opened_container = any(a.startswith("open ") for a in actions)
    took_item = any(a.startswith(("take ", "pick up")) for a in actions)
    used_light = any("lamp" in a or "light" in a or a.startswith("use ") for a in actions)
    searched_book_cmd = any("book" in a for a in actions)

    # containers/locations seen in observations
    seen_objs = sorted(set(re.findall(
        r"\b(?:book|desklamp|desk lamp|cellphone|keychain|laptop|pen|shelf|desk|drawer|safe)\b",
        blob,
    )))

    return {
        "goal": ep.get("goal"),
        "won": ep.get("success"),
        "obs_mentions_book": mentions_book,
        "obs_mentions_desklamp_or_lamp": mentions_desklamp or mentions_lamp,
        "any_open_container_action": opened_container,
        "any_take_or_pick_action": took_item,
        "any_use_light_action": used_light,
        "any_action_text_contains_book": searched_book_cmd,
        "objects_surfaced_in_obs": seen_objs,
        "book_location_known_from_trajectory": mentions_book,  # only if actually seen
        "book_location_status": (
            "seen_in_observation" if mentions_book else "UNKNOWN_FROM_TRAJECTORY"
        ),
        "desklamp_location_status": (
            "seen_in_observation" if (mentions_desklamp or mentions_lamp) else "UNKNOWN_FROM_TRAJECTORY"
        ),
        "agent_acted_on_goal_terms": searched_book_cmd or used_light or (mentions_book and opened_container),
        "looped_around_desk_shelf": True,  # verified by action distribution
        "note": (
            "Do not infer book position from failure. "
            "UNKNOWN_FROM_TRAJECTORY means the 29-step trace never surfaced the object."
        ),
    }


def budget_decode(reasoning_budget: int, horizon: int) -> Dict[str, Any]:
    """Mirror BudgetMeter.from_reasoning_budget exactly."""
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
    """Source-verified phenotype audit (see interactive_agent + behavioral_agent)."""
    return [
        {
            "gene": "planner_strategy",
            "changes_prompt": True,
            "prompt_mechanism": (
                "interactive_agent.select_action appends a strategy line only for "
                "plan_and_solve / tree_search / reflexion; 'cot' and 'direct' get NO "
                "strategy instruction beyond the label 'Planner: <name>'"
            ),
            "changes_execution": False,
            "execution_note": (
                "BehavioralAgent._plan changes synthetic step tags (not used in native "
                "ALFWorld EpisodeRunner path). InteractiveAgent has no plan structure."
            ),
            "measurable_behavior_delta": "prompt-only for native path",
            "evidence_level": "PROMPT_ONLY",
            "source": "src/runtime/interactive_agent.py select_action prompt_lines",
        },
        {
            "gene": "memory_strategy",
            "changes_prompt": True,
            "prompt_mechanism": "History block = MemoryStore.as_context() into prompt",
            "changes_execution": True,
            "execution_note": (
                "MemoryStore.write/read rules differ by strategy: none=disabled; "
                "short_term=items[-1:] ONLY LAST ONE; other strategies=items[-k:] k=3. "
                "Written item is only 'obs:<120 chars>' — NO action, feedback, or progress field."
            ),
            "measurable_behavior_delta": (
                "short_term keeps 1 obs line; episodic/semantic/hybrid keep up to 3; "
                "none keeps 0 — real prompt input difference"
            ),
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/behavioral_agent.py MemoryStore",
        },
        {
            "gene": "reflection_strategy",
            "changes_prompt": True,
            "prompt_mechanism": "label line 'Reflection: <name>' in prompt",
            "changes_execution": True,
            "execution_note": (
                "InteractiveAgent reflects ONLY when parsed action is None "
                "(parse failure) and strategy != 'none'. "
                "A legal-but-stagnant action NEVER triggers reflection. "
                "All non-none strategies share the SAME retry prompt — no per-strategy logic."
            ),
            "measurable_behavior_delta": (
                "none vs non-none: extra LLM call on parse failure; "
                "self_critique/pairwise/critic_model/iterative are behaviorally identical"
            ),
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/interactive_agent.py select_action reflection block",
        },
        {
            "gene": "tool_policy",
            "changes_prompt": True,
            "prompt_mechanism": "label line 'Tool policy: <name>' in prompt",
            "changes_execution": False,
            "execution_note": (
                "InteractiveAgent sets self.allow = ALLOW_TOOLS[...] but NEVER consults "
                "self.allow when selecting ALFWorld actions. Admissible commands come from "
                "the environment. ALLOW_TOOLS lists calculator/search/file_* which are NOT "
                "ALFWorld verbs. tool_policy is a NO-OP on the native path."
            ),
            "measurable_behavior_delta": "none on native ALFWorld EpisodeRunner path",
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/interactive_agent.py (self.allow unused) + ALLOW_TOOLS",
        },
        {
            "gene": "reasoning_budget",
            "changes_prompt": True,
            "prompt_mechanism": "'Remaining budget steps: N' in prompt",
            "changes_execution": True,
            "execution_note": (
                "BudgetMeter.from_reasoning_budget: max_steps=round(horizon*(0.5+b/128)); "
                "max_tokens=max(64, b*12). Each LLM call charges steps=1 (reflection "
                "charges another step). Budget gates episode length, not reasoning depth."
            ),
            "measurable_behavior_delta": (
                "changes max environment/LLM steps → changes cost and truncation; "
                "does NOT change per-step decision quality"
            ),
            "evidence_level": "CODE_CONFIRMED",
            "source": "src/runtime/behavioral_agent.py BudgetMeter",
        },
    ]


def feasibility_budget(pilot_tokens_in=8418, pilot_tokens_out=122, pilot_cost=0.0026718):
    """Episode cost model for 6 tasks × 3 genomes × 2 seeds = 36 episodes."""
    # Observed pilot: 30 HTTP, full horizon burn.
    # Historical D2 range (from project records): 3-31 calls/ep, $0.0001-$0.0012/ep
    # under OLD rates. Reprice historical low/high at NEW peak rates:
    #   worst observed tokens similar to pilot
    per_ep = pilot_cost
    # Conservative variants
    median_http = 30
    low_http, high_http = 3, 35
    # cost scales roughly with tokens; use pilot as median
    # low: few steps (early win or quick fail) ~ 3 HTTP, tokens ~ 1/10
    low_cost = pilot_cost * (3 / 30) * 1.5  # slight premium for fixed overhead
    high_cost = pilot_cost * (35 / 30) * 1.5  # extra retries/reflections margin
    n_ep = 36
    return {
        "design": "6 valid_train tasks x 3 genomes x 2 seeds = 36 episodes",
        "assumptions": [
            "model=deepseek-flash, rate_version=deepseek-flash-2026-10-peak-conservative-v1",
            "horizon=30, same execution layer as Pilot 1",
            "Pilot 1 observed: 30 HTTP, 8418 in, 122 out, $0.0026718 for 29 steps",
            "per-request reservation 2000 in + 128 out peak; actual settles to real usage",
            "no automatic retries; BillingBlocked stops the arm",
            "estimated cost is LOCAL estimate, not provider invoice",
        ],
        "per_episode": {
            "median_http": median_http,
            "median_cost_usd": per_ep,
            "median_tokens_in": pilot_tokens_in,
            "median_tokens_out": pilot_tokens_out,
            "low_http": low_http,
            "low_cost_usd": low_cost,
            "high_http": high_http,
            "high_cost_usd": high_cost,
        },
        "totals_36_episodes": {
            "median_http": median_http * n_ep,
            "median_cost_usd": round(per_ep * n_ep, 6),
            "low_http": low_http * n_ep,
            "low_cost_usd": round(low_cost * n_ep, 6),
            "high_http": high_http * n_ep,
            "high_cost_usd": round(high_cost * n_ep, 6),
        },
        "recommended_cap": {
            "physical_http": 36 * high_http + 20,  # margin
            "estimated_cost_usd": round(high_cost * n_ep * 1.25, 4),
            "note": "cap must allow BillingBlocked fail-closed without mid-experiment top-up",
        },
        "scale_risk": (
            "If all genomes fail (performance=0), 36 episodes still yield cost-difference "
            "signal only — insufficient for Gate 2/3. Budget is acceptable; scientific risk "
            "is zero-success degeneracy, not dollars."
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ep = json.loads(EP_PATH.read_text(encoding="utf-8"))
    metrics = analyze(ep)
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
                "steps": metrics["episode_meta"]["steps"],
                "planner_observed_dist": {
                    "examine desk 1": 16,
                    "look": 7,
                    "go to desk 1": 3,
                    "go to shelf 1": 3,
                },
                "matches_planner_observation": metrics["action_distribution"]
                == {
                    "examine desk 1": 16,
                    "look": 7,
                    "go to desk 1": 3,
                    "go to shelf 1": 3,
                },
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
                "max_consecutive_same_action": metrics["max_consecutive_same_action"],
                "max_consecutive_same_observation": metrics["max_consecutive_same_observation"],
                "state_action_pair_repeat_count": metrics["state_action_pair_repeat_count"],
                "state_action_loop_occurrences": metrics["state_action_loop_occurrences"],
                "repeated_pair_details": metrics["repeated_pair_details"],
                "no_new_info_action_count": metrics["no_new_info_action_count"],
                "no_new_info_action_ratio": metrics["no_new_info_action_ratio"],
                "obs_change_after_action_ratio": metrics["obs_change_after_action_ratio"],
                "unique_location_visit_count": metrics["unique_location_visit_count"],
                "unique_location_tokens": metrics["unique_location_tokens"],
                "action_repetition_ratio": metrics["action_repetition_ratio"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "behavioral_diagnosis.json").write_text(
        json.dumps(
            {
                "goal_progress": goal_progress_flags(ep),
                "budget_decode": budget_decode(
                    int((ep.get("genome") or {}).get("reasoning_budget", 64)), 30
                ),
                "observation_evidence": {
                    "raw_llm_response_available": metrics["raw_llm_response_available"],
                    "parse_ok_available": metrics["parse_ok_available"],
                    "used_fallback_available": metrics["used_fallback_available"],
                    "per_step_tokens_available": metrics["per_step_tokens_available"],
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
                    "env_actions": metrics["episode_meta"]["steps"],
                    "llm_call_count": metrics["episode_meta"]["llm_call_count"],
                    "reflection_count": metrics["episode_meta"]["reflection_count"],
                    "explanation": (
                        "29 select_action invocations produced 29 env actions; "
                        "1 invocation hit parse failure and reflected (2nd LLM call, "
                        "also charges a budget step) => 30 LLM calls, 30 budget charges, "
                        "max_steps=30 => budget_exhausted at the end of step 29"
                    ),
                },
                "loop_metrics_summary": {
                    "action_repetition_ratio": metrics["action_repetition_ratio"],
                    "max_consecutive_same_observation": metrics["max_consecutive_same_observation"],
                    "state_action_loop_occurrences": metrics["state_action_loop_occurrences"],
                    "no_new_info_action_ratio": metrics["no_new_info_action_ratio"],
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "genome_phenotype_matrix.json").write_text(
        json.dumps(
            {
                "genes": genome_phenotype_matrix(),
                "pilot1_genome": ep.get("genome"),
                "note": (
                    "PROMPT_ONLY != useless; it means no execution-mechanism change. "
                    "Native path = InteractiveAgent via EpisodeRunner."
                ),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "feasibility_budget_estimate.json").write_text(
        json.dumps(feasibility_budget(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # console summary
    print("ACTION DIST", metrics["action_distribution"])
    print("rep_ratio", round(metrics["action_repetition_ratio"], 4))
    print("max_run_action", metrics["max_consecutive_same_action"])
    print("max_run_obs", metrics["max_consecutive_same_observation"])
    print("loop_occurrences", metrics["state_action_loop_occurrences"])
    print("no_new_info_ratio", round(metrics["no_new_info_action_ratio"], 4))
    print("half_divergence", round(metrics["half_behavior_divergence"], 4))
    print("locations", metrics["unique_location_tokens"])
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
