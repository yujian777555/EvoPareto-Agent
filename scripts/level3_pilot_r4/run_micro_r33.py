"""R3 real-model experiment entry (Docker/IPC). Default is MOCK rehearsal.

Real mode requires DEEPSEEK_API_KEY and is NOT authorized in R3.2 — only
--mock runs are permitted this round (0 real HTTP, $0).

Every real request would go through independent R3 ledger with pre-send
remaining budget checks (reserve worst-case before send).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output
from src.research.r3_docker_executor import execute_candidate_docker
from src.research.r3_mutation_feedback import (
    FailureRecord,
    apply_random_mutation,
    build_feedback_child,
    hash_program,
    summarize_feedback,
)
from src.research.r4_workflow_program import load_frozen_parent
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_PHYSICAL = 55
MAX_COST_USD = 0.05
MAX_IN, MAX_OUT = 1500, 300
SEED = 20260603
TRAIN = ROOT / "results/level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
TRAIN_SHA256 = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"

SCREENING = [5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752]
DEV = [4336, 2201, 2495, 5648, 4346]
CONFIRM = [3098, 6031, 4459, 6404, 2184, 1856, 856, 4627]
PRIOR_USED = set(range(0, 8)) | {6245, 499, 6996, 4900, 2518, 3741, 475, 5516, 2354, 1139, 1066, 3324, 7193}

FIXTURE_OK = "Compute. Answer: 12345"
FIXTURE_WRONG = "Step by step. Answer: -999"


class R3Ledger:
    """Durable, append-only request ledger with pre-send reservation."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.events_path = self.path.with_suffix(".jsonl")
        if self.path.exists() or self.events_path.exists():
            raise FileExistsError("OUTPUT_LEDGER_EXISTS")
        self.rows: List[Dict[str, Any]] = []
        self.n = 0
        self.cost = 0.0
        self.budget_committed = 0.0
        self.pending: Dict[str, float] = {}
        self.stop: Optional[str] = None
        self.run_id = uuid.uuid4().hex
        self._snapshot()

    def _append_event(self, event: str, payload: Dict[str, Any]) -> None:
        record = {
            "event": event,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _snapshot(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.dump(), fh, indent=2, sort_keys=True, ensure_ascii=False, default=str)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def _blocked(self, reason: str, *, task_id: str, phase: str, estimated_input_tokens: Optional[int] = None) -> Dict[str, Any]:
        self.stop = self.stop or reason
        self._append_event("REQUEST_BLOCKED", {
            "reason": reason,
            "task_id": task_id,
            "phase": phase,
            "estimated_input_tokens": estimated_input_tokens,
        })
        self._snapshot()
        return {"ok": False, "error": self.stop, "skipped": True}

    def reserve(self, prompt: str, *, task_id: str, phase: str) -> Dict[str, Any]:
        """Persist a worst-case reservation before any network send."""
        if self.stop:
            return self._blocked(self.stop, task_id=task_id, phase=phase)
        if self.n >= MAX_PHYSICAL:
            return self._blocked("REQUEST_CAP_REACHED", task_id=task_id, phase=phase)
        est_in = conservative_input_tokens(prompt)
        if est_in > MAX_IN:
            return self._blocked(
                "INPUT_TOKEN_CAP_EXCEEDED",
                task_id=task_id,
                phase=phase,
                estimated_input_tokens=est_in,
            )
        reserve = worst_case_cost(MODEL_ID, MAX_IN, MAX_OUT)
        pending_cost = sum(self.pending.values())
        if self.budget_committed + pending_cost + reserve > MAX_COST_USD + 1e-12:
            return self._blocked("COST_RESERVE_EXCEEDED", task_id=task_id, phase=phase, estimated_input_tokens=est_in)
        request_id = uuid.uuid4().hex
        row = {
            "request_id": request_id,
            "phase": phase,
            "task_id": task_id,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "estimated_input_tokens": est_in,
            "reserved_cost_usd": reserve,
            "state": "RESERVED",
            "billing_status": "PENDING",
        }
        self.rows.append(row)
        self.pending[request_id] = reserve
        self._append_event("PRE_SEND_RESERVED", dict(row))
        self._snapshot()
        return {"ok": True, "request_id": request_id, "reserved_cost_usd": reserve}

    def mark_sending(self, request_id: str) -> None:
        row = self._find(request_id)
        row["state"] = "SENDING"
        row["send_intent_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        self.n += 1  # conservatively counts a request before the socket operation
        self._append_event("SEND_INTENT_DURABLE", dict(row))
        self._snapshot()

    def _find(self, request_id: str) -> Dict[str, Any]:
        for row in self.rows:
            if row["request_id"] == request_id:
                return row
        raise KeyError("UNKNOWN_REQUEST_ID")

    def settle(
        self,
        request_id: str,
        *,
        details: Dict[str, Any],
        billing_known: bool,
        actual_cost: Optional[float] = None,
        stop_reason: Optional[str] = None,
    ) -> None:
        row = self._find(request_id)
        reserve = self.pending.pop(request_id)
        row.update(details)
        if billing_known and actual_cost is not None:
            charge = max(0.0, float(actual_cost))
            self.cost += charge
            self.budget_committed += charge
            row["actual_cost_usd"] = charge
            row["budget_charged_usd"] = charge
            row["billing_status"] = "KNOWN"
            row["state"] = "SETTLED"
            if charge > reserve + 1e-12:
                self.stop = self.stop or "ACTUAL_COST_EXCEEDED_RESERVATION"
            if self.budget_committed > MAX_COST_USD + 1e-12:
                self.stop = self.stop or "ACTUAL_BUDGET_CAP_EXCEEDED"
        else:
            # Unknown billing is charged against the budget at the full reserved bound.
            self.budget_committed += reserve
            row["actual_cost_usd"] = None
            row["budget_charged_usd"] = reserve
            row["billing_status"] = "UNKNOWN_RESERVED_AT_WORST_CASE"
            row["state"] = "BILLING_UNKNOWN"
            self.stop = self.stop or stop_reason or "BILLING_UNCERTAIN"
        if stop_reason:
            self.stop = self.stop or stop_reason
        row["stop_reason"] = self.stop
        self._append_event("REQUEST_SETTLED", dict(row))
        self._snapshot()

    def usage_for(self, task_id: str, phase: str) -> Dict[str, Any]:
        rows = [
            row for row in self.rows
            if row.get("task_id") == task_id and row.get("phase") == phase
        ]
        return {
            "total_cost": round(sum(float(r.get("actual_cost_usd") or 0.0) for r in rows), 10),
            "total_input_tokens": sum(int(r.get("tokens_in") or 0) for r in rows),
            "total_output_tokens": sum(int(r.get("tokens_out") or 0) for r in rows),
            "physical_requests": sum(1 for r in rows if r.get("state") in ("SENDING", "SETTLED", "BILLING_UNKNOWN")),
        }

    def dump(self) -> Dict[str, Any]:
        pending = sum(self.pending.values())
        return {
            "evidence_class": "REAL_OR_MOCK_R3_3_LEDGER",
            "run_id": self.run_id,
            "model": MODEL_ID,
            "n_physical_requests": self.n,
            "actual_cost_usd": round(self.cost, 8),
            "budget_charged_upper_bound_usd": round(self.budget_committed + pending, 8),
            "pending_reserved_usd": round(pending, 8),
            "stop_reason": self.stop,
            "max_physical": MAX_PHYSICAL,
            "max_cost_usd": MAX_COST_USD,
            "event_log": self.events_path.name,
            "requests": self.rows,
        }
def real_chat(prompt: str, ledger: R3Ledger, *, task_id: str, phase: str) -> Dict[str, Any]:
    """Send one direct DeepSeek request under a durable fail-closed budget gate."""
    reservation = ledger.reserve(prompt, task_id=task_id, phase=phase)
    if not reservation.get("ok"):
        return {"ok": False, "error": reservation.get("error"), "content": "", "skipped": True}

    request_id = reservation["request_id"]
    body = json.dumps({
        "model": MODEL_ID,
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_OUT,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # bypass system/global proxy
    ledger.mark_sending(request_id)
    t0 = time.time()
    try:
        with opener.open(req, timeout=45) as resp:
            raw = resp.read()
            status = int(resp.status)
    except Exception as exc:
        ledger.settle(
            request_id,
            details={
                "error": f"{type(exc).__name__}:{exc}",
                "http_status": getattr(exc, "code", None),
                "settle": "fail_closed_unknown",
                "latency_s": round(time.time() - t0, 3),
            },
            billing_known=False,
            stop_reason="TRANSPORT_OR_HTTP_ERROR",
        )
        return {"ok": False, "error": "TRANSPORT_OR_HTTP_ERROR", "content": ""}

    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("RESPONSE_NOT_OBJECT")
    except Exception as exc:
        ledger.settle(
            request_id,
            details={
                "http_status": status,
                "error": f"INVALID_JSON:{type(exc).__name__}",
                "settle": "fail_closed_unknown",
                "latency_s": round(time.time() - t0, 3),
            },
            billing_known=False,
            stop_reason="INVALID_JSON_BILLING_UNKNOWN",
        )
        return {"ok": False, "error": "INVALID_JSON_BILLING_UNKNOWN", "content": ""}

    usage = data.get("usage")
    required_usage = ("prompt_tokens", "completion_tokens")
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in required_usage):
        ledger.settle(
            request_id,
            details={
                "http_status": status,
                "error": "USAGE_MISSING_OR_INVALID",
                "settle": "fail_closed_unknown",
                "latency_s": round(time.time() - t0, 3),
            },
            billing_known=False,
            stop_reason="USAGE_MISSING_OR_INVALID",
        )
        return {"ok": False, "error": "USAGE_MISSING_OR_INVALID", "content": ""}

    tokens_in = usage["prompt_tokens"]
    tokens_out = usage["completion_tokens"]
    actual_cost = estimate_cost(MODEL_ID, tokens_in, tokens_out, peak=True)
    response_model = data.get("model")
    choices = data.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content") or ""

    invalid_reason = None
    if status != 200:
        invalid_reason = "HTTP_STATUS_NOT_200"
    elif response_model != MODEL_ID:
        invalid_reason = "RESPONSE_MODEL_MISMATCH"
    elif tokens_in > MAX_IN or tokens_out > MAX_OUT:
        invalid_reason = "PROVIDER_TOKEN_CAP_EXCEEDED"
    elif not isinstance(content, str) or not content.strip():
        invalid_reason = "EMPTY_MODEL_CONTENT"

    ledger.settle(
        request_id,
        details={
            "http_status": status,
            "response_model": response_model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": actual_cost,
            "usage_raw": usage,
            "latency_s": round(time.time() - t0, 3),
            "settle": "settled_actual",
            "error": invalid_reason,
        },
        billing_known=True,
        actual_cost=actual_cost,
        stop_reason=invalid_reason,
    )
    if invalid_reason or ledger.stop:
        return {"ok": False, "error": invalid_reason or ledger.stop, "content": "", "cost_usd": actual_cost}
    return {"ok": True, "content": content, "cost_usd": actual_cost}

class RealIPCMailbox:
    """Host-side mailbox bridging Docker IPC to real_chat / mock fixture."""

    def __init__(self, ledger: R3Ledger, task_id: str, phase: str, mock_response: Optional[str] = None, mock_mode: bool = False):
        self.ledger = ledger
        self.task_id = task_id
        self.phase = phase
        self.mock_response = mock_response
        self.mock_mode = mock_mode
        self.calls: List[str] = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        if self.mock_mode:
            if self.mock_response is None:
                raise RuntimeError("FIXTURE_NOT_CONFIGURED")
            # mock does not debit real ledger
            return self.mock_response
        r = real_chat(str(prompt), self.ledger, task_id=self.task_id, phase=self.phase)
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "MODEL_FAIL")
        return r.get("content") or ""

    def get_usage_summary(self):
        if self.mock_mode:
            return {"total_cost": 0.0, "total_input_tokens": 0, "total_output_tokens": 0}
        return self.ledger.usage_for(self.task_id, self.phase)


def load_rows():
    rows = {}
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
            rows[i] = {"index": i, "question": o["question"], "answer_raw": ans, "gold": " ".join(gold.split())}
    return rows


def to_task(i, row):
    return GSM8KTask(f"gsm8k-train-{i:04d}", row["question"], row["gold"], row["answer_raw"], "train")


def run_arm(prog, tasks, *, ledger, phase, mock_mode, extra_fixtures=None):
    fixtures = extra_fixtures or {}
    out = []
    for t in tasks:
        if not mock_mode and ledger.stop:
            break
        if mock_mode:
            if t.task_id not in fixtures or not fixtures[t.task_id]:
                raise RuntimeError(f"MOCK_FIXTURE_NOT_CONFIGURED:{t.task_id}")
            mock_resp = fixtures[t.task_id]
        else:
            mock_resp = None
        box = RealIPCMailbox(ledger, t.task_id, phase, mock_response=mock_resp, mock_mode=mock_mode)
        try:
            r = execute_candidate_docker(
                prog,
                t.question,
                llm=box,
                task_id=t.task_id,
                expect_graph_sha256=hash_program(prog),
            )
        except Exception as exc:
            r = {
                "ok": False,
                "error": f"{type(exc).__name__}:{exc}",
                "answer_text": None,
                "executed_graph_source": False,
                "graph_sha256_match": False,
                "n_llm_calls": 0,
            }
        execution_valid = bool(
            r.get("ok") is True
            and r.get("executed_graph_source") is True
            and r.get("graph_sha256_match") is True
            and r.get("answer_text") is not None
        )
        sc = evaluate_workflow_output(t, r.get("answer_text") or "") if execution_valid else {"predicted": None, "correct": False}
        out.append({
            "task_id": t.task_id,
            "program_id": r.get("program_id"),
            "graph_sha256": r.get("graph_sha256"),
            "graph_sha256_match": r.get("graph_sha256_match"),
            "executed_graph_source": r.get("executed_graph_source"),
            "execution_valid": execution_valid,
            "ok": r.get("ok"),
            "n_llm_calls": r.get("n_llm_calls"),
            "predicted": sc.get("predicted"),
            "correct": bool(sc.get("correct")) if execution_valid else None,
            "parse_valid": sc.get("predicted") is not None if execution_valid else False,
            "error": r.get("error"),
            "phase": phase,
            "fixture": mock_resp if mock_mode else None,
        })
        if not execution_valid:
            break
    return out


def require_valid_arm(name: str, rows: List[Dict[str, Any]], tasks) -> None:
    if len(rows) != len(tasks):
        raise RuntimeError(f"ARM_INCOMPLETE:{name}:rows={len(rows)} expected={len(tasks)}")
    invalid = [r for r in rows if not r.get("execution_valid")]
    if invalid:
        first = invalid[0]
        raise RuntimeError(
            f"ARM_EXECUTION_INVALID:{name}:task={first.get('task_id')}:error={first.get('error')}"
        )


def accuracy(rows: List[Dict[str, Any]]) -> float:
    if not rows or any(r.get("correct") is None for r in rows):
        raise ValueError("ACCURACY_REQUIRES_COMPLETE_VALID_ROWS")
    return sum(1 for r in rows if r["correct"]) / len(rows)


def paired_comparison(base_rows: List[Dict[str, Any]], candidate_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = {r["task_id"]: r for r in base_rows}
    candidate = {r["task_id"]: r for r in candidate_rows}
    if len(base) != len(base_rows) or len(candidate) != len(candidate_rows) or set(base) != set(candidate):
        raise ValueError("PAIRED_TASK_SET_MISMATCH")
    both_correct = base_only = candidate_only = both_wrong = 0
    for task_id in sorted(base):
        a, b = base[task_id], candidate[task_id]
        if not a.get("execution_valid") or not b.get("execution_valid"):
            raise ValueError(f"PAIRED_INVALID_EXECUTION:{task_id}")
        av, bv = a.get("correct"), b.get("correct")
        if not isinstance(av, bool) or not isinstance(bv, bool):
            raise ValueError(f"PAIRED_MISSING_SCORE:{task_id}")
        if av and bv:
            both_correct += 1
        elif av and not bv:
            base_only += 1
        elif not av and bv:
            candidate_only += 1
        else:
            both_wrong += 1
    discordant = base_only + candidate_only
    if discordant == 0:
        p_exact = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(min(base_only, candidate_only) + 1))
        p_exact = min(1.0, 2.0 * tail / (2 ** discordant))
    n = len(base_rows)
    return {
        "n": n,
        "base_accuracy": sum(1 for r in base_rows if r["correct"]) / n if n else None,
        "candidate_accuracy": sum(1 for r in candidate_rows if r["correct"]) / n if n else None,
        "both_correct": both_correct,
        "base_only_correct": base_only,
        "candidate_only_correct": candidate_only,
        "both_wrong": both_wrong,
        "mcnemar_exact_p_two_sided": p_exact,
        "interpretation": "EXPLORATORY_ONLY_NOT_CONFIRMATORY",
    }
def main() -> int:
    ap = argparse.ArgumentParser()
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--mock", action="store_true", help="explicit zero-API simulated rehearsal")
    modes.add_argument("--real", action="store_true", help="run the capped DeepSeek real-model micro-pilot")
    ap.add_argument("--out", default=None, help="new, empty output directory; never overwrite prior evidence")
    args = ap.parse_args()
    mock_mode = not args.real
    if args.real and not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing; no request sent")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_mode = "real" if args.real else "mock"
    outdir = Path(args.out) if args.out else ROOT / "results" / f"level3_pilot_r4_micro_r33_{default_mode}_{stamp}"
    if outdir.exists() and any(outdir.iterdir()):
        print(f"BLOCKED: output directory is not empty: {outdir}")
        return 3
    outdir.mkdir(parents=True, exist_ok=True)

    ledger = None
    stage = "preflight"
    try:
        if not TRAIN.exists():
            raise RuntimeError(f"TRAIN_DATA_MISSING:{TRAIN}")
        actual_train_sha = hashlib.sha256(TRAIN.read_bytes()).hexdigest()
        if actual_train_sha != TRAIN_SHA256:
            raise RuntimeError(f"TRAIN_DATA_SHA_MISMATCH:{actual_train_sha}")
        if len(set(DEV)) != len(DEV) or len(set(CONFIRM)) != len(CONFIRM):
            raise RuntimeError("DUPLICATE_TASK_INDEX")
        if set(DEV) & set(CONFIRM):
            raise RuntimeError("DEV_CONFIRM_OVERLAP")
        all_new = set(SCREENING) | set(DEV) | set(CONFIRM)
        if len(all_new) != 23 or (all_new & PRIOR_USED):
            raise RuntimeError("TASK_SPLIT_CONTAMINATION")
        rows = load_rows()
        missing = sorted((set(DEV) | set(CONFIRM)) - set(rows))
        if missing:
            raise RuntimeError(f"TASK_INDEX_OUT_OF_RANGE:{missing}")
        parent = load_frozen_parent(FROZEN)
        dev_tasks = [to_task(i, rows[i]) for i in DEV]
        conf_tasks = [to_task(i, rows[i]) for i in CONFIRM]
        ledger = R3Ledger(outdir / "request_ledger.json")
        protocol = {
            "protocol": "MICRO-R3.3",
            "evidence_class": "SIMULATED_REHEARSAL" if mock_mode else "REAL_MODEL",
            "mode": "mock" if mock_mode else "real",
            "seed": SEED,
            "model": MODEL_ID,
            "base_url": BASE_URL,
            "proxy_bypass": True,
            "train_sha256": actual_train_sha,
            "screening_indices": SCREENING,
            "dev_indices": DEV,
            "confirm_indices": CONFIRM,
            "splits_disjoint": True,
            "confirm_used_for_selection": False,
            "expected_episode_calls_upper_bound": 44,
            "budget": {
                "baseline_requests": 50,
                "max_physical_requests": MAX_PHYSICAL,
                "max_cost_usd": MAX_COST_USD,
                "max_input_tokens_per_request": MAX_IN,
                "max_output_tokens_per_request": MAX_OUT,
                "reservation_per_request_usd": worst_case_cost(MODEL_ID, MAX_IN, MAX_OUT),
            },
            "claims": "Exploratory GSM8K micro-pilot only; not thesis-mainline evidence and not a confirmatory RSI claim.",
        }
        (outdir / "protocol.json").write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        # In Mock mode, every task must have an explicit task-keyed fixture.
        dev_fixtures = {t.task_id: FIXTURE_OK for t in dev_tasks}
        conf_fixtures = {t.task_id: FIXTURE_OK for t in conf_tasks}
        parent_dev_fixtures = dict(dev_fixtures)
        parent_dev_fixtures[dev_tasks[0].task_id] = FIXTURE_WRONG

        stage = "dev:P"
        parent_dev = run_arm(parent, dev_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=parent_dev_fixtures)
        require_valid_arm(stage, parent_dev, dev_tasks)
        parent_summary = summarize_feedback([
            FailureRecord(
                task_id=t.task_id,
                parent_program_id=parent.program_id,
                parent_graph_sha256=hash_program(parent),
                success=bool(row["correct"]),
                error_category="NO_FAILURE" if row["correct"] else ("ANSWER_MISMATCH" if row.get("predicted") is not None else "PARSE_ERROR"),
                predicted=row.get("predicted"),
                gold=t.gold_answer,
                diagnosis_uses_gold=True,
            )
            for t, row in zip(dev_tasks, parent_dev)
        ])

        child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
        if child_r is None:
            raise RuntimeError(f"RANDOM_MUTATION_FAILED:{rec_r}")
        stage = "dev:R"
        r_rows = run_arm(child_r, dev_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=dev_fixtures)
        require_valid_arm(stage, r_rows, dev_tasks)
        candidates = {"R": (child_r, r_rows, rec_r)}
        scores = {"R": accuracy(r_rows)}

        child_f, rec_f = build_feedback_child(parent, parent_summary, seed=SEED, slot=2)
        f_rows = []
        if child_f is not None:
            stage = "dev:F"
            f_rows = run_arm(child_f, dev_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=dev_fixtures)
            require_valid_arm(stage, f_rows, dev_tasks)
            candidates["F"] = (child_f, f_rows, rec_f)
            scores["F"] = accuracy(f_rows)

        winner_name = max(scores, key=lambda name: (scores[name], name == "R"))
        winner, winner_rows, _ = candidates[winner_name]
        winner_records = [
            FailureRecord(
                task_id=t.task_id,
                parent_program_id=winner.program_id,
                parent_graph_sha256=hash_program(winner),
                success=bool(row["correct"]),
                error_category="NO_FAILURE" if row["correct"] else ("ANSWER_MISMATCH" if row.get("predicted") is not None else "PARSE_ERROR"),
                predicted=row.get("predicted"),
                gold=t.gold_answer,
                diagnosis_uses_gold=True,
            )
            for t, row in zip(dev_tasks, winner_rows)
        ]
        winner_summary = summarize_feedback(winner_records)
        e2, rec_e2 = build_feedback_child(winner, winner_summary, seed=SEED, slot=3)
        e2_rows = []
        if e2 is not None:
            stage = "dev:E2"
            e2_rows = run_arm(e2, dev_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=dev_fixtures)
            require_valid_arm(stage, e2_rows, dev_tasks)

        stage = "confirm:P"
        p_conf = run_arm(parent, conf_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=conf_fixtures)
        require_valid_arm(stage, p_conf, conf_tasks)
        stage = "confirm:winner"
        w_conf = run_arm(winner, conf_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=conf_fixtures)
        require_valid_arm(stage, w_conf, conf_tasks)
        e_conf = []
        if e2 is not None:
            stage = "confirm:E2"
            e_conf = run_arm(e2, conf_tasks, ledger=ledger, phase=stage, mock_mode=mock_mode, extra_fixtures=conf_fixtures)
            require_valid_arm(stage, e_conf, conf_tasks)

        paired = {"P_vs_winner": paired_comparison(p_conf, w_conf)}
        if e2 is not None:
            paired["P_vs_E2"] = paired_comparison(p_conf, e_conf)
            paired["winner_vs_E2"] = paired_comparison(w_conf, e_conf)

        summary = {
            "protocol": "MICRO-R3.3",
            "evidence_class": "SIMULATED_REHEARSAL" if mock_mode else "REAL_MODEL",
            "mode": "mock" if mock_mode else "real",
            "mock_mode": mock_mode,
            "seed": SEED,
            "dev_scores": scores,
            "gen1_winner": winner_name,
            "winner_dev_accuracy": accuracy(winner_rows),
            "e2_parent_ok": (rec_e2.get("parent_program_id") == winner.program_id) if e2 is not None else False,
            "e2_generation": e2.generation if e2 is not None else None,
            "e2_status": rec_e2.get("status"),
            "e2_feedback_label": rec_e2.get("feedback_label") or rec_e2.get("reason"),
            "requests_total": ledger.n,
            "cost_usd_total": round(ledger.cost, 8),
            "budget_charged_upper_bound_usd": ledger.dump()["budget_charged_upper_bound_usd"],
            "billing_uncertain": any(r.get("billing_status") == "UNKNOWN_RESERVED_AT_WORST_CASE" for r in ledger.rows),
            "budget_baseline_requests": 50,
            "budget_suggested_cap_requests": MAX_PHYSICAL,
            "budget_cap_usd": MAX_COST_USD,
            "confirm_used_for_selection": False,
            "paired_analysis": paired,
            "statistical_claim": "EXPLORATORY_MICRO_PILOT_ONLY_NO_CONFIRMATORY_CLAIM",
        }
        (outdir / "candidate_lineage.json").write_text(json.dumps({
            "P": {"program_id": parent.program_id, "graph_sha256": hash_program(parent), "generation": 0},
            "R": rec_r,
            "F": rec_f,
            "winner": {"arm": winner_name, "program_id": winner.program_id, "graph_sha256": hash_program(winner), "generation": winner.generation},
            "E2": rec_e2,
        }, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        (outdir / "paired_results.json").write_text(json.dumps({
            "dev": {"P": parent_dev, "R": r_rows, "F": f_rows, "E2": e2_rows},
            "confirm": {"P": p_conf, "winner": w_conf, "E2": e_conf},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (outdir / "paired_analysis.json").write_text(json.dumps(paired, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (outdir / "request_ledger.json").write_text(json.dumps(ledger.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (outdir / "REPORT.md").write_text(
            "# MICRO-R3.3 run report\n\n"
            f"Mode: **{'SIMULATED rehearsal' if mock_mode else 'REAL DeepSeek model'}**\n\n"
            f"- requests={ledger.n}\n"
            f"- actual known cost USD={ledger.cost:.8f}\n"
            f"- budget charged upper bound USD={ledger.dump()['budget_charged_upper_bound_usd']:.8f}\n"
            f"- gen-1 winner={winner_name}; dev scores={scores}\n"
            f"- confirmation paired analysis={json.dumps(paired, sort_keys=True)}\n\n"
            "This is an exploratory GSM8K micro-pilot only. Mock results are not model-performance evidence. "
            "Eight confirmation tasks do not support a confirmatory recursive-self-improvement claim.\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "protocol": "MICRO-R3.3",
            "evidence_class": "REAL_MODEL" if args.real else "SIMULATED_REHEARSAL",
            "mode": "real" if args.real else "mock",
            "stage": stage,
            "error": f"{type(exc).__name__}:{exc}",
            "no_confirmatory_claim": True,
            "ledger": ledger.dump() if ledger is not None else None,
        }
        (outdir / "ABORTED.json").write_text(json.dumps(failure, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        (outdir / "REPORT.md").write_text(
            "# MICRO-R3.3 aborted\n\n"
            f"- stage={stage}\n- error={type(exc).__name__}: {exc}\n"
            "- Interpret as an aborted/invalid run, not as a negative model result.\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, indent=2, sort_keys=True, default=str))
        return 10

if __name__ == "__main__":
    raise SystemExit(main())
