"""Stage 1.5 failure taxonomy + parser reconciliation + seed semantics.

Reads Stage 1 real episodes + DecisionLogs. 0 API calls.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
EPDIR = ROOT / "results/stage1_feasibility/episodes"
OUT = ROOT / "results/stage1_5"


def load() -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(EPDIR.glob("*.json"))]


# progress stage evidence rules (documented)
STAGE_RULES = {
    "GOAL_IDENTIFIED": "goal text non-empty in episode",
    "OBJECT_DISCOVERED": "any observation mentions the target object type (env feedback)",
    "OBJECT_ACQUIRED": "any action startswith take/pick of target object",
    "INTERMEDIATE_STATE": "task-type specific: light toggled (use *lamp*) or object moved to target receptacle",
    "FINAL_GOAL_ATTEMPTED": "look at <obj> or the win-achieving action (use lamp while holding / move to target)",
    "NATIVE_WON": "episode success == True",
}

TARGET = {
    0: {"obj": "book", "recep": "desklamp", "type": "look_at_obj_in_light"},
    10: {"obj": "laptop", "recep": "desklamp", "type": "look_at_obj_in_light"},
    20: {"obj": "alarmclock", "recep": "dresser", "type": "pick_and_place_simple"},
}


def classify(ep: Dict[str, Any]) -> Dict[str, Any]:
    tidx = ep.get("task_index")
    meta = TARGET.get(int(tidx) if tidx is not None else -1, {"obj": "", "recep": "", "type": ""})
    obj, recep = meta["obj"], meta["recep"]
    logs = ep.get("decision_logs") or []
    traj = ep.get("trajectory") or []
    actions = [str(d.get("executed_action") or "") for d in logs] or [str(t.get("action") or "") for t in traj]
    obs_blob = "\n".join(str(t.get("observation_before") or "") + "\n" + str(t.get("observation_after") or "") for t in traj).lower()
    act_l = [a.lower() for a in actions]

    # strip task description from obs for discovery
    import re
    pure = re.sub(r"^\s*your task is to:.*$", "", obs_blob, flags=re.I | re.M)

    discovered = bool(re.search(rf"\b{obj}\b", pure)) if obj else False
    acquired = any(obj in a and (a.startswith("take ") or a.startswith("pick")) for a in act_l) if obj else False
    toggled = any(a.startswith("use ") and "lamp" in a for a in act_l)
    moved_to_target = any(
        (a.startswith("move ") or a.startswith("put ")) and obj in a and recep in a
        for a in act_l
    ) if obj and recep else False
    final_attempt = any(a.startswith("look at ") and obj in a for a in act_l) or toggled or moved_to_target
    won = bool(ep.get("won", ep.get("success")))

    # loop / budget
    pair_c = Counter()
    for t in traj:
        pair_c[(str(t.get("observation_before") or "").strip(), str(t.get("action") or ""))] += 1
    loop_occ = sum(c - 1 for c in pair_c.values() if c > 1)
    term = ep.get("termination_reason", "")

    labels = []
    if won:
        labels.append("SUCCESS")
    if not discovered:
        labels.append("OBJECT_NOT_FOUND")
    elif discovered and not acquired:
        labels.append("OBJECT_FOUND_BUT_NOT_ACQUIRED")
    if acquired and not won:
        labels.append("OBJECT_ACQUIRED_BUT_GOAL_NOT_COMPLETED")
    if loop_occ >= 5:
        labels.append("LOOP_STAGNATION")
    if term == "budget_exhausted":
        labels.append("BUDGET_EXHAUSTED")
    if term == "env_done" and not won:
        labels.append("ENVIRONMENT_TERMINATED")
    if any(d.get("used_fallback") for d in logs):
        labels.append("ACTION_PARSE_FAILURE")
    if not labels:
        labels.append("UNKNOWN_CAUSE")

    # first-discovery remaining steps
    first_disc_step = None
    for i, t in enumerate(traj):
        o = (str(t.get("observation_after") or "") + str(t.get("observation_before") or "")).lower()
        if obj and re.search(rf"\b{obj}\b", re.sub(r"your task is to:.*", "", o, flags=re.I)):
            first_disc_step = i + 1
            break
    steps = ep.get("steps") or len(traj)
    remaining_after_discovery = (steps - first_disc_step) if first_disc_step else None

    return {
        "episode_id": ep.get("episode_id"),
        "task_index": tidx,
        "genome_id": ep.get("genome_id"),
        "seed": ep.get("seed"),
        "task_type": meta["type"],
        "won": won,
        "labels": labels,
        "progress": {
            "goal_identified": bool(ep.get("goal")),
            "object_discovered": discovered,
            "object_acquired": acquired,
            "intermediate_state": toggled or moved_to_target,
            "final_goal_attempted": final_attempt,
            "native_won": won,
        },
        "evidence": {
            "first_discovery_step": first_disc_step,
            "steps_after_first_discovery": remaining_after_discovery,
            "loop_occurrences": loop_occ,
            "termination_reason": term,
            "sample_target_actions": [a for a in actions if obj and obj in a.lower()][:8],
            "sample_lamp_actions": [a for a in actions if "lamp" in a.lower()][:6],
        },
    }


def parser_reconciliation(eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    first_fail = 0
    reflection_attempt = 0
    reflection_recovered = 0
    final_fail = 0
    fallback_used = 0
    total_decisions = 0
    per_ep = []
    for ep in eps:
        logs = ep.get("decision_logs") or []
        ef = er = err = ff = fb = 0
        for d in logs:
            total_decisions += 1
            parse_ok = bool(d.get("parse_ok", True))
            reflected = bool(d.get("reflection_trigger"))
            if not parse_ok and not reflected:
                # parse failed and no reflection (strategy none or failed)
                first_fail += 1
                ef += 1
                final_fail += 1
                ff += 1
            elif not parse_ok and reflected:
                # shouldn't happen: parse_ok is final status after reflection
                first_fail += 1
                ef += 1
            if reflected:
                reflection_attempt += 1
                er += 1
                if parse_ok:
                    reflection_recovered += 1
                    err += 1
            if d.get("used_fallback"):
                fallback_used += 1
                fb += 1
            # FIRST_PARSE_FAILURE: parse_fail_reason non-empty means first parse failed
            # DecisionLog records final parse_ok; reflection_trigger implies first failed
        # recount first-parse-failure properly from raw fields
        per_ep.append({
            "episode_id": ep.get("episode_id"),
            "decisions": len(logs),
            "final_parse_failures": sum(1 for d in logs if not d.get("parse_ok", True)),
            "reflections": sum(1 for d in logs if d.get("reflection_trigger")),
            "fallbacks": sum(1 for d in logs if d.get("used_fallback")),
            "first_parse_failure_inferred": sum(
                1 for d in logs
                if (not d.get("parse_ok", True)) or d.get("reflection_trigger")
            ),
        })
    # first parse failure = decisions where reflection fired OR final parse failed
    first_parse_failure = sum(e["first_parse_failure_inferred"] for e in per_ep)
    return {
        "definitions": {
            "FIRST_PARSE_FAILURE": "decision where initial parse failed (final parse_ok=False OR reflection_trigger set)",
            "REFLECTION_ATTEMPT": "decision with reflection_trigger non-empty",
            "REFLECTION_RECOVERED": "reflection_attempt AND final parse_ok=True",
            "FINAL_PARSE_FAILURE": "final parse_ok=False (includes after reflection failed)",
            "FALLBACK_USED": "used_fallback=True",
        },
        "total_decisions": total_decisions,
        "FIRST_PARSE_FAILURE": first_parse_failure,
        "REFLECTION_ATTEMPT": reflection_attempt,
        "REFLECTION_RECOVERED": reflection_recovered,
        "FINAL_PARSE_FAILURE": final_fail,
        "FALLBACK_USED": fallback_used,
        "note": "parse failure != fallback: reflection can repair; fallback only when both parses fail and strategy allows",
        "per_episode": per_ep,
    }


def seed_semantics() -> Dict[str, Any]:
    return {
        "seeds_used": [11, 23],
        "control_surface_audit": {
            "python_random": "NOT seeded by EpisodeRunner seed parameter in Stage 1 path",
            "numpy": "NOT used in native episode loop",
            "torch": "NOT used",
            "alfworld_reset": "force_game_file locks the game; reset index is 0; seed not passed to AlfredTWEnv",
            "task_selection": "frozen manifest index — not random",
            "genome_mutation": "N/A (Stage 1 evaluates fixed genomes)",
            "llm_sampling": "DeepSeek API call has NO seed parameter set; temperature not set (provider default); sampling is NOT controlled by episode seed",
        },
        "verdict": "SEED_NOT_EFFECTIVE_FOR_LIVE_POLICY",
        "explanation": (
            "seed=11 vs seed=23 only label the episode. Forced game loading + "
            "no explicit LLM seed means trajectories differ only from LLM sampling "
            "noise, not from a controlled RNG the experimenter set. They are NOT "
            "strict independent controlled replicates."
        ),
        "recommendation_for_future": [
            "treat seed as a batch label only until LLM provider exposes a seed",
            "use more episodes per cell rather than 2 pseudo-replicates",
            "report per-episode outcomes, not significance tests on n=2",
            "if temperature is fixed later, apply the same setting to all arms",
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    eps = load()
    rows = [classify(ep) for ep in eps]

    by_type: Dict[str, List[str]] = defaultdict(list)
    by_g: Dict[str, List[str]] = defaultdict(list)
    label_count: Counter = Counter()
    for r in rows:
        for lb in r["labels"]:
            label_count[lb] += 1
            by_type[r["task_type"]].append(lb)
            by_g[str(r["genome_id"])].append(lb)

    found_not_won = sum(1 for r in rows if r["progress"]["object_discovered"] and not r["won"])
    acquired_not_won = sum(1 for r in rows if r["progress"]["object_acquired"] and not r["won"])
    final_attempt_not_won = sum(1 for r in rows if r["progress"]["final_goal_attempted"] and not r["won"])

    failure_classification = {
        "taxonomy_definitions": STAGE_RULES,
        "n_episodes": len(rows),
        "label_counts": dict(label_count),
        "by_task_type": {k: dict(Counter(v)) for k, v in by_type.items()},
        "by_genome": {k: dict(Counter(v)) for k, v in by_g.items()},
        "object_found_but_failed_count": found_not_won,
        "object_acquired_but_failed_count": acquired_not_won,
        "final_goal_attempted_but_failed_count": final_attempt_not_won,
        "progress_stage_histogram": {
            stage: sum(1 for r in rows if r["progress"][stage])
            for stage in ("goal_identified", "object_discovered", "object_acquired",
                          "intermediate_state", "final_goal_attempted", "native_won")
        },
        "episodes": rows,
    }
    (OUT / "failure_classification.json").write_text(
        json.dumps(failure_classification, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    parser = parser_reconciliation(eps)
    (OUT / "parser_failure_reconciliation.json").write_text(
        json.dumps(parser, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    (OUT / "seed_semantics.json").write_text(
        json.dumps(seed_semantics(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("labels", dict(label_count))
    print("progress histogram", failure_classification["progress_stage_histogram"])
    print("parser", {k: parser[k] for k in ("FIRST_PARSE_FAILURE", "REFLECTION_ATTEMPT", "REFLECTION_RECOVERED", "FINAL_PARSE_FAILURE", "FALLBACK_USED")})
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
