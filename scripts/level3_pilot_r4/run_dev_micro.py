"""LEVEL3-PILOT-R4 micro exploratory experiment (real DeepSeek).

Independent micro budget: max 50 physical HTTP requests, max $0.05.
Not the formal R4 confirmation experiment. Formal R4 freeze remains unapproved.

Reuses: GSM8K scoring, provider cost estimates, r4_workflow_program candidates,
proxy-bypass direct HTTP (same as R3), host-side gold scoring.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output
from src.research.r4_workflow_program import (
    build_group_c_fixed_verify,
    load_frozen_parent,
    mutate_add_sampling,
    mutate_insert_instruction,
    program_provenance,
)
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

# ---- Micro budget policy (versioned, independent of formal R4 policy) ----
MICRO_POLICY_VERSION = "R4-MICRO-BUDGET-v1"
MAX_PHYSICAL_REQUESTS = 50
MAX_COST_USD = 0.05
MAX_IN_TOKENS = 1500
MAX_OUT_TOKENS = 300
MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
# peak prices used by provider_gateway; keep explicit for transparency
PRICE_IN_PER_1M = 0.30
PRICE_OUT_PER_1M = 1.20

OUT = ROOT / "results" / "level3_pilot_r4_micro_exploratory"
TRAIN = ROOT / "results" / "level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
AUTH_PATH = ROOT / "results" / "level3_pilot_r4_micro_exploratory" / "micro_authorization.json"

SEED = 20260601
DEV_N = 5
HOLD_N = 3


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_first_n_train(n: int) -> List[Dict[str, Any]]:
    rows = []
    with TRAIN.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append(obj)
            if len(rows) >= n:
                break
    return rows


def to_task(i: int, obj: Dict[str, Any]) -> GSM8KTask:
    ans = obj["answer"]
    gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
    gold = " ".join(gold.split())
    return GSM8KTask(
        task_id=f"gsm8k-train-{i:04d}",
        question=obj["question"],
        gold_answer=gold,
        gold_raw=ans,
        split="train",
    )


class MicroLedger:
    """Independent micro ledger (JSON). Fail-closed on caps. Not the formal auth ledger."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: List[Dict[str, Any]] = []
        self.n_physical = 0
        self.cost_usd = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.stop_reason: Optional[str] = None

    def check_before_send(self, est_in: int) -> str:
        if self.stop_reason:
            return self.stop_reason
        if self.n_physical >= MAX_PHYSICAL_REQUESTS:
            self.stop_reason = "REQUEST_CAP_REACHED"
            return self.stop_reason
        if self.cost_usd >= MAX_COST_USD:
            self.stop_reason = "COST_CAP_REACHED"
            return self.stop_reason
        if est_in > MAX_IN_TOKENS:
            self.stop_reason = "INPUT_TOKEN_CAP"
            return self.stop_reason
        return ""

    def record(self, row: Dict[str, Any]) -> None:
        self.rows.append(row)
        self.n_physical += 1
        self.cost_usd += float(row.get("cost_usd") or 0.0)
        self.tokens_in += int(row.get("tokens_in") or 0)
        self.tokens_out += int(row.get("tokens_out") or 0)

    def dump(self) -> Dict[str, Any]:
        return {
            "evidence_class": "REAL_MODEL_MICRO_LEDGER",
            "policy_version": MICRO_POLICY_VERSION,
            "max_physical_requests": MAX_PHYSICAL_REQUESTS,
            "max_cost_usd": MAX_COST_USD,
            "model": MODEL_ID,
            "n_physical_requests": self.n_physical,
            "total_cost_usd": round(self.cost_usd, 8),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "stop_reason": self.stop_reason,
            "requests": self.rows,
        }


def real_chat(prompt: str, ledger: MicroLedger, *, phase: str, task_id: str) -> Dict[str, Any]:
    est_in = conservative_input_tokens(prompt)
    err = ledger.check_before_send(est_in)
    if err:
        return {"ok": False, "error": err, "content": "", "cost_usd": 0.0, "skipped": True}
    # reserve worst-case then send
    reserve = worst_case_cost(MODEL_ID, min(est_in, MAX_IN_TOKENS), MAX_OUT_TOKENS)
    body = json.dumps({
        "model": MODEL_ID,
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_OUT_TOKENS,
        "messages": [{"role": "user", "content": prompt[: MAX_IN_TOKENS * 3]}],
    }).encode("utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # direct, bypass proxy
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        },
    )
    row: Dict[str, Any] = {
        "phase": phase,
        "task_id": task_id,
        "prompt_sha256": sha256_text(prompt),
        "estimated_input_tokens": est_in,
        "reserved_cost_usd": reserve,
    }
    t0 = time.time()
    try:
        with opener.open(req, timeout=90) as resp:
            raw = resp.read()
            status = int(resp.status)
        row["http_status"] = status
        row["latency_s"] = round(time.time() - t0, 3)
    except Exception as e:
        row.update({"error": f"{type(e).__name__}:{e}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
        ledger.record(row)
        return {"ok": False, "error": row["error"], "content": "", "cost_usd": 0.0}

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        row.update({"error": f"JSON:{type(e).__name__}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
        ledger.record(row)
        return {"ok": False, "error": row["error"], "content": "", "cost_usd": 0.0}

    usage = data.get("usage") or {}
    t_in = int(usage.get("prompt_tokens") or 0)
    t_out = int(usage.get("completion_tokens") or 0)
    choices = data.get("choices") or []
    content = ""
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
    cost = estimate_cost(MODEL_ID, t_in, t_out, peak=True)
    row.update({
        "tokens_in": t_in,
        "tokens_out": t_out,
        "cost_usd": cost,
        "finish_reason": (choices[0].get("finish_reason") if choices else None),
        "settle": "settled_actual",
        "usage_raw": usage,
    })
    ledger.record(row)
    ok = status == 200 and content is not None
    return {"ok": ok, "content": content, "cost_usd": cost, "tokens_in": t_in, "tokens_out": t_out}


# ---- Candidate definitions ----

FIXED_C1_INSTRUCTION = "Solve step by step, end with 'Answer: <num>'."


def build_candidates(dev_scores_gen1: Optional[Dict[str, float]] = None):
    parent = load_frozen_parent(FROZEN)
    cand = {"P": parent}
    # C1: instruction mutation
    c1 = mutate_insert_instruction(parent, instruction=FIXED_C1_INSTRUCTION)
    cand["C1"] = c1
    # C2: 2-sample vote
    c2 = mutate_add_sampling(parent, n_samples=2)
    cand["C2"] = c2
    return parent, cand


def apply_c3_from(winner) -> Any:
    # non-empty non-duplicate instruction mutation
    instr = "Verify each step, then output the final number after 'Answer:'."
    if getattr(winner, "instruction", None) == instr:
        instr = "Compute carefully. Put the numeric result after 'Answer:'."
    return mutate_insert_instruction(winner, instruction=instr)


def run_program_on_question(prog, task: GSM8KTask, ledger: MicroLedger, *, phase: str) -> Dict[str, Any]:
    """Execute candidate against one question with real API calls."""
    q = task.question
    calls = []
    try:
        if prog.n_samples >= 2 or prog.aggregation == "majority_vote":
            n = int(prog.n_samples)
            drafts = []
            for i in range(n):
                prompt = f"{prog.instruction or 'Solve step by step.'}\n{q}\nEnd with 'Answer: <num>'."
                r = real_chat(prompt, ledger, phase=f"{phase}:sample{i+1}", task_id=task.task_id)
                calls.append(r)
                if not r.get("ok"):
                    # fail closed this candidate-task
                    return {"ok": False, "error": r.get("error"), "content": "", "n_calls": len(calls), "correct": False}
                drafts.append(r.get("content") or "")
            # deterministic majority on extracted tails
            from src.research.r4_workflow_program import majority_vote_deterministic

            votes = [d.strip().split("Answer:")[-1].strip().split()[-1] if d.strip() else "" for d in drafts]
            votes = [v.strip(" .,;") for v in votes]
            best = majority_vote_deterministic(votes) if votes else ""
            raw = "\n".join(drafts) + f"\nAnswer: {best}"
        else:
            instr = prog.instruction or ""
            prompt = f"{instr}\n{q}\nEnd with 'Answer: <num>'." if instr else f"{q}\nEnd with 'Answer: <num>'."
            r = real_chat(prompt, ledger, phase=phase, task_id=task.task_id)
            calls.append(r)
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error"), "content": "", "n_calls": 1, "correct": False}
            raw = r.get("content") or ""
        sc = evaluate_workflow_output(task, raw)
        return {
            "ok": True,
            "content": raw,
            "n_calls": len(calls),
            "correct": bool(sc["correct"]),
            "predicted": sc.get("predicted"),
            "score": sc,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}", "content": "", "n_calls": len(calls), "correct": False}


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    rows = load_first_n_train(DEV_N + HOLD_N)
    dev_tasks = [to_task(i, rows[i]) for i in range(DEV_N)]
    hold_tasks = [to_task(DEV_N + i, rows[DEV_N + i]) for i in range(HOLD_N)]

    parent, cand = build_candidates()
    lineage = []
    for name, p in cand.items():
        prov = program_provenance(p)
        lineage.append({
            "id": name,
            "program_id": p.program_id,
            "parent_program_id": p.parent_program_id,
            "generation": p.generation,
            "operator_history": p.operator_history,
            "instruction": p.instruction,
            "n_samples": p.n_samples,
            "aggregation": p.aggregation,
            "graph_sha256": prov["graph_sha256"],
            "instruction_sha256": prov["instruction_sha256"],
            "seed": SEED,
        })

    ledger = MicroLedger(OUT / "request_ledger.json")

    protocol = {
        "evidence_class": "REAL_MODEL_MICRO_EXPLORATORY",
        "experiment": "LEVEL3-PILOT-R4 micro exploratory (dev 5 / holdout 3)",
        "note": "NOT formal R4 confirmation. 3 holdout tasks => directional only.",
        "model": MODEL_ID,
        "base_url": BASE_URL,
        "seed": SEED,
        "dataset": {
            "file": str(TRAIN.relative_to(ROOT)),
            "sha256": hashlib.sha256(TRAIN.read_bytes()).hexdigest(),
            "record_count_used": DEV_N + HOLD_N,
            "selection": "first 8 official train records in file order",
            "dev_task_ids": [t.task_id for t in dev_tasks],
            "holdout_task_ids": [t.task_id for t in hold_tasks],
            "uses_official_test": False,
            "uses_formal_confirmation_set": False,
        },
        "candidates_initial": lineage,
        "micro_budget": {
            "policy_version": MICRO_POLICY_VERSION,
            "max_physical_requests": MAX_PHYSICAL_REQUESTS,
            "max_cost_usd": MAX_COST_USD,
            "max_in_tokens": MAX_IN_TOKENS,
            "max_out_tokens": MAX_OUT_TOKENS,
            "estimated_normal_requests": 45,
        },
        "selection_rule": "max dev accuracy; tie -> order P < C1 < C2 then C3",
        "holdout_compare": ["P", "GEN1_WINNER", "C3"],
    }
    (OUT / "protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # ---- Phase 1: evaluate P, C1, C2 on dev ----
    order = ["P", "C1", "C2"]
    dev_results: Dict[str, List[Dict[str, Any]]] = {k: [] for k in order}
    for name in order:
        for t in dev_tasks:
            if ledger.stop_reason:
                dev_results[name].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
                continue
            r = run_program_on_question(cand[name], t, ledger, phase=f"dev:{name}")
            dev_results[name].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})

    def acc(name: str) -> float:
        rows_ = dev_results[name]
        return sum(1 for x in rows_ if x.get("correct")) / max(1, len(rows_))

    scores = {name: acc(name) for name in order}
    # tie -> order
    winner = max(order, key=lambda n: (scores[n], -order.index(n)))
    print("DEV scores", scores, "winner", winner)

    # ---- C3 from winner ----
    c3 = apply_c3_from(cand[winner])
    cand["C3"] = c3
    lineage.append({
        "id": "C3",
        "program_id": c3.program_id,
        "parent_program_id": c3.parent_program_id,
        "generation": c3.generation,
        "operator_history": c3.operator_history,
        "instruction": c3.instruction,
        "n_samples": c3.n_samples,
        "aggregation": c3.aggregation,
        **{k: v for k, v in program_provenance(c3).items() if k.endswith("sha256")},
        "seed": SEED,
        "derived_from": winner,
    })
    dev_results["C3"] = []
    for t in dev_tasks:
        if ledger.stop_reason:
            dev_results["C3"].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
            continue
        r = run_program_on_question(c3, t, ledger, phase="dev:C3")
        dev_results["C3"].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})
    scores["C3"] = acc("C3")

    # ---- Phase 2: holdout P, winner, C3 ----
    hold_arms = ["P", winner, "C3"]
    hold_results: Dict[str, List[Dict[str, Any]]] = {a: [] for a in hold_arms}
    for name in hold_arms:
        for t in hold_tasks:
            if ledger.stop_reason:
                hold_results[name].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
                continue
            r = run_program_on_question(cand[name], t, ledger, phase=f"hold:{name}")
            hold_results[name].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})

    def hold_acc(name: str) -> float:
        return sum(1 for x in hold_results[name] if x.get("correct")) / max(1, len(hold_results[name]))

    # paired deltas vs P
    def paired_vs_p(name: str) -> Tuple[int, int, List[str], List[str]]:
        improved, regressed = [], []
        for a, b in zip(hold_results["P"], hold_results[name]):
            if b.get("correct") and not a.get("correct"):
                improved.append(a["task_id"])
            elif a.get("correct") and not b.get("correct"):
                regressed.append(a["task_id"])
        return len(improved), len(regressed), improved, regressed

    imp_w, reg_w, imp_w_ids, reg_w_ids = paired_vs_p(winner)
    imp_3, reg_3, imp_3_ids, reg_3_ids = paired_vs_p("C3")
    imp_2, reg_2, imp_2_ids, reg_2_ids = (0, 0, [], [])
    if winner != "C3":
        # C3 vs winner
        for a, b in zip(hold_results[winner], hold_results["C3"]):
            if b.get("correct") and not a.get("correct"):
                imp_2 += 1
                imp_2_ids.append(a["task_id"])
            elif a.get("correct") and not b.get("correct"):
                reg_2 += 1
                reg_2_ids.append(a["task_id"])

    summary = {
        "evidence_class": "REAL_MODEL_MICRO_EXPLORATORY",
        "n_tasks_dev": DEV_N,
        "n_tasks_holdout": HOLD_N,
        "dev_scores": scores,
        "gen1_winner": winner,
        "holdout_accuracy": {a: hold_acc(a) for a in hold_arms},
        "paired_vs_parent_on_holdout": {
            winner: {"improved": imp_w, "regressed": reg_w, "improved_ids": imp_w_ids, "regressed_ids": reg_w_ids},
            "C3": {"improved": imp_3, "regressed": reg_3, "improved_ids": imp_3_ids, "regressed_ids": reg_3_ids},
        },
        "c3_vs_winner_on_holdout": {"improved": imp_2, "regressed": reg_2, "improved_ids": imp_2_ids, "regressed_ids": reg_2_ids},
        "requests_total": ledger.n_physical,
        "cost_usd_total": round(ledger.cost_usd, 8),
        "tokens_in": ledger.tokens_in,
        "tokens_out": ledger.tokens_out,
        "stop_reason": ledger.stop_reason,
        "statistical_claim": "NONE — 3 holdout tasks; directional engineering signal only; not significant; not RSI proof",
    }

    (OUT / "candidate_lineage.json").write_text(json.dumps({"evidence_class": "REAL_MODEL_MICRO_EXPLORATORY", "seed": SEED, "candidates": lineage}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "paired_results.json").write_text(json.dumps({"evidence_class": "REAL_MODEL_MICRO_EXPLORATORY", "dev": dev_results, "holdout": hold_results, "dev_scores": scores, "gen1_winner": winner}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "request_ledger.json").write_text(json.dumps(ledger.dump(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # REPORT.md
    lines = [
        "# LEVEL3-PILOT-R4 Micro Exploratory Report",
        "",
        f"- Model: `{MODEL_ID}` (real HTTP, proxy bypass direct)",
        f"- Dev: {DEV_N} tasks { [t.task_id for t in dev_tasks] }",
        f"- Holdout: {HOLD_N} tasks { [t.task_id for t in hold_tasks] }",
        f"- Physical requests: **{ledger.n_physical}** / {MAX_PHYSICAL_REQUESTS}",
        f"- Actual cost: **${ledger.cost_usd:.6f}** / ${MAX_COST_USD}",
        f"- Tokens in/out: {ledger.tokens_in} / {ledger.tokens_out}",
        f"- Stop reason: {ledger.stop_reason or 'completed'}",
        "",
        "## Dev accuracy (candidate selection)",
        "",
        "| Candidate | Dev acc |",
        "|---|---:|",
    ]
    for k in ["P", "C1", "C2", "C3"]:
        if k in scores:
            lines.append(f"| {k} | {scores[k]:.2f} |")
    lines += [
        "",
        f"**Gen-1 winner:** `{winner}`",
        "",
        "## Holdout accuracy (3 tasks, paired)",
        "",
        "| Arm | Acc | vs Parent improve/regress | vs winner improve/regress |",
        "|---|---:|---|---|",
        f"| P (Parent) | {hold_acc('P'):.2f} | — | — |",
        f"| {winner} | {hold_acc(winner):.2f} | {imp_w}/{reg_w} | — |",
        f"| C3 | {hold_acc('C3'):.2f} | {imp_3}/{reg_3} | {imp_2}/{reg_2} |",
        "",
        "## Interpretation (directional only)",
        "",
        f"1. First-gen vs Parent: improved {imp_w}, regressed {reg_w}.",
        f"2. Second-gen vs first-gen winner: improved {imp_2}, regressed {reg_2}.",
        f"3. Improved ids: {imp_w_ids + imp_3_ids}; regressed ids: {reg_w_ids + reg_3_ids}.",
        "4. Cost must be weighed against these tiny deltas (n=3 holdout).",
        "5. **No statistical significance. Not recursive self-improvement proof.**",
        "",
        "## Files",
        "",
        "- `protocol.json`, `candidate_lineage.json`, `request_ledger.json`, `paired_results.json`, `summary.json`",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("SUMMARY", json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
