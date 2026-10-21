"""LEVEL3-PILOT-R4-MICRO-R2: difficulty-stratified parent/child paired experiment.

Real deepseek-flash. Independent micro budget: 50 physical requests, $0.05.
Not formal R4. Not RSI proof.

Research questions (from brief):
  1. On harder tasks, can children beat frozen Parent?
  2. Random mutation vs feedback-driven mutation — which looks more promising?
  3. Can gen-2 inherit gen-1 gains?
  4. After controlling for multi-sample voting, do evolutionary candidates still win?

Candidates (Task B table in the brief was truncated in delivery; implemented
against the four RQs above):
  P  — frozen Parent (single call)
  R  — random instruction mutation (single call)
  F  — feedback-driven mutation: instruction asks for self-check (single call)
  S  — sampling control: Parent instruction + 2-sample vote (isolates voting)
  E2 — gen-2 instruction mutation from the better of {R,F} on dev (single call)

Budget plan (single-call arms are 1 call/task; S is 2 calls/task):
  dev 5 tasks: P+R+F+E2 = 20 calls
  holdout 8 tasks: P+R+F+E2 = 32 calls  -> 52 over
  instead holdout arms P, R, F, E2 on all 8 = 32; drop nothing
  OR holdout P+winner+E2 = 24; total 44; + S probe on 3 holdout (6) = 50

Chosen: dev 5 (P,R,F) + E2(5) = 20; holdout 8 (P, R, F, E2) would be 52.
Final: holdout 8 (P, gen1_best, E2) = 24; plus S sampling probe on 3 holdout = 6;
total = 5+5+5+5 + 8+8+8 + 6 = 50 exactly.

RQ2 (R vs F) compared on dev (5) + 3 holdout overlap is limited; full R vs F
comparison is on dev only due to budget — reported honestly.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output
from src.research.r4_workflow_program import (
    load_frozen_parent,
    majority_vote_deterministic,
    mutate_add_sampling,
    mutate_insert_instruction,
    program_provenance,
)
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

MICRO_POLICY_VERSION = "R4-MICRO2-BUDGET-v1"
MAX_PHYSICAL_REQUESTS = 50
MAX_COST_USD = 0.05
MAX_IN_TOKENS = 1500
MAX_OUT_TOKENS = 300
MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"

OUT = ROOT / "results" / "level3_pilot_r4_micro_r2"
TRAIN = ROOT / "results" / "level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"

SEED = 20260602
PREV_USED_INDICES = set(range(0, 8))  # MICRO-R1 used train indices 0..7
DEV_N = 5
HOLD_N = 8
S_PROBE_N = 3


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class MicroLedger:
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
        return {"ok": False, "error": err, "content": "", "skipped": True}
    reserve = worst_case_cost(MODEL_ID, min(est_in, MAX_IN_TOKENS), MAX_OUT_TOKENS)
    body = json.dumps({
        "model": MODEL_ID,
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_OUT_TOKENS,
        "messages": [{"role": "user", "content": prompt[: MAX_IN_TOKENS * 3]}],
    }).encode("utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
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
        return {"ok": False, "error": row["error"], "content": ""}
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        row.update({"error": f"JSON:{type(e).__name__}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
        ledger.record(row)
        return {"ok": False, "error": row["error"], "content": ""}
    usage = data.get("usage") or {}
    t_in = int(usage.get("prompt_tokens") or 0)
    t_out = int(usage.get("completion_tokens") or 0)
    choices = data.get("choices") or []
    content = ""
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
    cost = estimate_cost(MODEL_ID, t_in, t_out, peak=True)
    row.update({
        "tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost,
        "finish_reason": (choices[0].get("finish_reason") if choices else None),
        "settle": "settled_actual", "usage_raw": usage,
    })
    ledger.record(row)
    return {"ok": status == 200, "content": content, "cost_usd": cost}


def to_task(i: int, obj: Dict[str, Any]) -> GSM8KTask:
    ans = obj["answer_raw"] if "answer_raw" in obj else obj["answer"]
    gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
    gold = " ".join(gold.split())
    return GSM8KTask(task_id=f"gsm8k-train-{i:04d}", question=obj["question"], gold_answer=gold, gold_raw=ans, split="train")


def load_and_stratify():
    rows = []
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
            rows.append({
                "index": i,
                "question": o["question"],
                "answer_raw": ans,
                "gold": " ".join(gold.split()),
                "sol_len": len(ans.split()),
            })
    pool = [r for r in rows if r["index"] not in PREV_USED_INDICES]
    lens = sorted(r["sol_len"] for r in pool)
    c1, c2 = lens[int(len(lens) * 0.33)], lens[int(len(lens) * 0.66)]
    short = [r for r in pool if r["sol_len"] <= c1]
    mid = [r for r in pool if c1 < r["sol_len"] <= c2]
    long = [r for r in pool if r["sol_len"] > c2]
    rng = random.Random(SEED)

    def take(stratum, n):
        idxs = list(range(len(stratum)))
        rng.shuffle(idxs)
        return [stratum[i] for i in idxs[:n]]

    dev = take(short, 2) + take(mid, 2) + take(long, 1)
    dev_idx = {d["index"] for d in dev}
    hold = take(short, 3) + take(mid, 3) + take(long, 2)
    hold = [h for h in hold if h["index"] not in dev_idx][:HOLD_N]
    # refill holdout if needed
    used = dev_idx | {h["index"] for h in hold}
    for stratum, n in ((short, 3), (mid, 3), (long, 2)):
        extra_needed = 0
        # keep simple: pull more from remaining pool
    if len(hold) < HOLD_N:
        for r in pool:
            if r["index"] not in used and len(hold) < HOLD_N:
                hold.append(r)
                used.add(r["index"])
    assert len(dev) == DEV_N, len(dev)
    assert len(hold) == HOLD_N, len(hold)
    cuts = {"short_max": c1, "mid_max": c2, "note": "solution-word-count difficulty PROXY, not true difficulty label"}
    return rows, dev, hold, cuts


def build_candidates():
    parent = load_frozen_parent(FROZEN)
    c_r = mutate_insert_instruction(parent, instruction="Give a short guess quickly. End with 'Answer: <num>'.")
    c_f = mutate_insert_instruction(
        parent,
        instruction="Solve step by step, check the arithmetic once, then end with 'Answer: <num>'.",
    )
    c_s = mutate_add_sampling(parent, n_samples=2)
    return parent, c_r, c_f, c_s


def build_e2(winner_prog):
    # non-empty non-duplicate instruction mutation from gen-1 winner
    instr = "Re-read the question, recompute, then end with 'Answer: <num>'."
    if getattr(winner_prog, "instruction", None) == instr:
        instr = "Double-check units and arithmetic. End with 'Answer: <num>'."
    return mutate_insert_instruction(winner_prog, instruction=instr)


def run_prog(prog, task: GSM8KTask, ledger: MicroLedger, phase: str) -> Dict[str, Any]:
    q = task.question
    calls = 0
    try:
        if prog.aggregation == "majority_vote" or prog.n_samples >= 2:
            drafts = []
            for i in range(int(prog.n_samples)):
                prompt = f"{prog.instruction or 'Solve step by step.'}\n{q}\nEnd with 'Answer: <num>'."
                r = real_chat(prompt, ledger, phase=f"{phase}:s{i+1}", task_id=task.task_id)
                calls += 1
                if not r.get("ok"):
                    return {"ok": False, "error": r.get("error"), "n_calls": calls, "correct": False, "predicted": None}
                drafts.append(r.get("content") or "")
            votes = []
            for d in drafts:
                tail = d.strip().split("Answer:")[-1].strip()
                parts = tail.split()
                votes.append(parts[-1].strip(" .,;") if parts else "")
            best = majority_vote_deterministic(votes) if votes else ""
            raw = "\n".join(drafts) + f"\nAnswer: {best}"
        else:
            instr = prog.instruction or ""
            prompt = f"{instr}\n{q}\nEnd with 'Answer: <num>'." if instr else f"{q}\nEnd with 'Answer: <num>'."
            r = real_chat(prompt, ledger, phase=phase, task_id=task.task_id)
            calls += 1
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error"), "n_calls": calls, "correct": False, "predicted": None}
            raw = r.get("content") or ""
        sc = evaluate_workflow_output(task, raw)
        return {"ok": True, "n_calls": calls, "correct": bool(sc["correct"]), "predicted": sc.get("predicted"), "content_len": len(raw)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}", "n_calls": calls, "correct": False, "predicted": None}


def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    _, dev_rows, hold_rows, cuts = load_and_stratify()
    dev_tasks = [to_task(d["index"], d) for d in dev_rows]
    hold_tasks = [to_task(h["index"], h) for h in hold_rows]

    parent, c_r, c_f, c_s = build_candidates()
    cand = {"P": parent, "R": c_r, "F": c_f, "S": c_s}

    def lineage_entry(name, p, **extra):
        prov = program_provenance(p)
        return {
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
            **extra,
        }

    lineage = [lineage_entry(n, cand[n]) for n in ("P", "R", "F", "S")]

    protocol = {
        "evidence_class": "REAL_MODEL_MICRO_EXPLORATORY_R2",
        "experiment": "LEVEL3-PILOT-R4-MICRO-R2 difficulty-stratified",
        "note": "NOT formal R4. Directional engineering signal only.",
        "model": MODEL_ID,
        "seed": SEED,
        "dataset": {
            "file": str(TRAIN.relative_to(ROOT)),
            "sha256": TRAIN_SHA,
            "excluded_prior_used_indices": sorted(PREV_USED_INDICES),
            "stratification": cuts,
            "stratum_rule": "solution word-count tertiles on unused pool (difficulty PROXY)",
            "dev_indices": [t.task_id for t in dev_tasks],
            "holdout_indices": [t.task_id for t in hold_tasks],
            "dev_n": DEV_N,
            "holdout_n": HOLD_N,
            "uses_official_test": False,
            "uses_formal_confirmation_set": False,
            "gold_never_in_prompt": True,
        },
        "candidates_initial": lineage,
        "micro_budget": {
            "policy_version": MICRO_POLICY_VERSION,
            "max_physical_requests": MAX_PHYSICAL_REQUESTS,
            "max_cost_usd": MAX_COST_USD,
            "max_in_tokens": MAX_IN_TOKENS,
            "max_out_tokens": MAX_OUT_TOKENS,
        },
        "research_questions": [
            "RQ1 harder tasks: children vs Parent",
            "RQ2 random (R) vs feedback-driven (F)",
            "RQ3 gen2 inherits gen1 gains",
            "RQ4 voting-controlled: S is sampling-only; R/F/E2 are single-call",
        ],
        "design_note": "Brief's Task B table was truncated at delivery; candidates implemented against the four stated RQs.",
        "selection_rule": "dev accuracy max among R,F; tie -> R before F (fixed order).",
    }
    (OUT / "protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    ledger = MicroLedger(OUT / "request_ledger.json")

    # ---- DEV: P, R, F ----
    dev_res = {"P": [], "R": [], "F": []}
    for name in ("P", "R", "F"):
        for t in dev_tasks:
            if ledger.stop_reason:
                dev_res[name].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
                continue
            r = run_prog(cand[name], t, ledger, phase=f"dev:{name}")
            dev_res[name].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})
            print("DEV", name, t.task_id, r.get("correct"), "reqs", ledger.n_physical)

    def acc(rows_):
        return sum(1 for x in rows_ if x.get("correct")) / max(1, len(rows_))

    dev_scores = {k: acc(v) for k, v in dev_res.items()}
    # gen1 winner among R,F (P is baseline)
    order = ["R", "F"]
    winner = max(order, key=lambda n: (dev_scores[n], -order.index(n)))
    print("DEV", dev_scores, "gen1_winner", winner)

    # ---- E2 from winner ----
    c_e2 = build_e2(cand[winner])
    cand["E2"] = c_e2
    lineage.append(lineage_entry("E2", c_e2, derived_from=winner))
    dev_res["E2"] = []
    for t in dev_tasks:
        if ledger.stop_reason:
            dev_res["E2"].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
            continue
        r = run_prog(c_e2, t, ledger, phase="dev:E2")
        dev_res["E2"].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})
        print("DEV E2", t.task_id, r.get("correct"), "reqs", ledger.n_physical)
    dev_scores["E2"] = acc(dev_res["E2"])

    # ---- HOLDOUT: P, gen1_winner, E2 ----
    hold_arms = ["P", winner, "E2"]
    hold_res = {a: [] for a in hold_arms}
    for name in hold_arms:
        for t in hold_tasks:
            if ledger.stop_reason:
                hold_res[name].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
                continue
            r = run_prog(cand[name], t, ledger, phase=f"hold:{name}")
            hold_res[name].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})
            print("HOLD", name, t.task_id, r.get("correct"), "reqs", ledger.n_physical)

    # S sampling probe on first S_PROBE_N holdout (voting confound control)
    hold_res["S"] = []
    for t in hold_tasks[:S_PROBE_N]:
        if ledger.stop_reason:
            hold_res["S"].append({"task_id": t.task_id, "ok": False, "error": ledger.stop_reason, "correct": False, "n_calls": 0})
            continue
        r = run_prog(cand["S"], t, ledger, phase="hold:S")
        hold_res["S"].append({"task_id": t.task_id, **{k: r.get(k) for k in ("ok", "n_calls", "correct", "predicted", "error")}})
        print("HOLD S", t.task_id, r.get("correct"), "reqs", ledger.n_physical)

    def hold_acc(a):
        return acc(hold_res[a])

    def paired(a, b):
        imp, reg = [], []
        for x, y in zip(hold_res[a], hold_res[b]):
            if y.get("correct") and not x.get("correct"):
                imp.append(x["task_id"])
            elif x.get("correct") and not y.get("correct"):
                reg.append(x["task_id"])
        return {"improved": len(imp), "regressed": len(reg), "improved_ids": imp, "regressed_ids": reg}

    summary = {
        "evidence_class": "REAL_MODEL_MICRO_EXPLORATORY_R2",
        "dev_scores": dev_scores,
        "gen1_winner": winner,
        "holdout_accuracy": {a: hold_acc(a) for a in hold_res},
        "paired_vs_P": {a: paired("P", a) for a in hold_res if a != "P"},
        "e2_vs_winner": paired(winner, "E2"),
        "rq2_dev_random_vs_feedback": {"R": dev_scores.get("R"), "F": dev_scores.get("F"), "winner": winner},
        "requests_total": ledger.n_physical,
        "cost_usd_total": round(ledger.cost_usd, 8),
        "tokens_in": ledger.tokens_in,
        "tokens_out": ledger.tokens_out,
        "stop_reason": ledger.stop_reason,
        "statistical_claim": "NONE — directional only; n_dev=5 n_hold=8; not significance; not RSI proof",
    }

    (OUT / "candidate_lineage.json").write_text(json.dumps({"evidence_class": "REAL_MODEL_MICRO_EXPLORATORY_R2", "seed": SEED, "candidates": lineage}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "paired_results.json").write_text(json.dumps({"evidence_class": "REAL_MODEL_MICRO_EXPLORATORY_R2", "dev": dev_res, "holdout": hold_res, "dev_scores": dev_scores, "gen1_winner": winner}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "request_ledger.json").write_text(json.dumps(ledger.dump(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# MICRO-R2 Report (difficulty-stratified)",
        "",
        f"- Model: `{MODEL_ID}` real HTTP (direct, proxy bypass)",
        f"- Seed: {SEED}; train SHA: `{TRAIN_SHA[:16]}…`",
        f"- Dev: {DEV_N} tasks; Holdout: {HOLD_N} tasks; S probe: {S_PROBE_N} holdout",
        f"- Physical requests: **{ledger.n_physical}**/{MAX_PHYSICAL_REQUESTS}; cost **${ledger.cost_usd:.6f}**/{MAX_COST_USD}",
        f"- Stop: {ledger.stop_reason or 'completed'}",
        "",
        "## Dev accuracy",
        "",
        "| Cand | Acc |",
        "|---|---:|",
    ]
    for k in ("P", "R", "F", "E2"):
        if k in dev_scores:
            lines.append(f"| {k} | {dev_scores[k]:.2f} |")
    lines += [
        "",
        f"**Gen-1 winner (R vs F):** `{winner}`",
        "",
        "## Holdout accuracy (paired vs P)",
        "",
        "| Arm | Acc | vs P imp/reg | vs winner imp/reg |",
        "|---|---:|---|---|",
    ]
    for a in hold_res:
        vs_p = summary["paired_vs_P"].get(a, {"improved": "—", "regressed": "—"})
        vs_w = summary["e2_vs_winner"] if a == "E2" else {"improved": "—", "regressed": "—"}
        lines.append(f"| {a} | {hold_acc(a):.2f} | {vs_p.get('improved')}/{vs_p.get('regressed')} | {vs_w.get('improved')}/{vs_w.get('regressed')} |")
    lines += [
        "",
        "## RQ answers (directional only)",
        "",
        f"1. Children vs Parent on harder tasks: see paired_vs_P; P acc={hold_acc('P'):.2f}.",
        f"2. Random R={dev_scores.get('R')} vs feedback F={dev_scores.get('F')} on dev; winner=`{winner}`.",
        f"3. E2 vs winner on holdout: imp={summary['e2_vs_winner']['improved']} reg={summary['e2_vs_winner']['regressed']}.",
        "4. S is a 2-sample voting control (confound isolation); R/F/E2 are single-call. Compare S vs single-call arms carefully.",
        "",
        "**No statistical significance. Not recursive self-improvement proof.**",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("SUMMARY", json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
