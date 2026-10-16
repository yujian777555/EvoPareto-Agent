"""Reconcile DeepSeek bill vs project-side token accounting."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1) SQLite ledgers (gated experiments)
ledgers = [
    "results/pilot1_live_run/budget.sqlite",
    "results/stage1_feasibility/budget.sqlite",
    "results/stage1_6/budget.sqlite",
    "results/stage1_8/budget.sqlite",
]
g_in = g_out = g_http = g_cost = 0
print("=== A. SQLite ledger ===")
for p in ledgers:
    f = ROOT / p
    if not f.exists():
        continue
    c = sqlite3.connect(str(f))
    c.row_factory = sqlite3.Row
    r = dict(c.execute("SELECT * FROM budget WHERE id=1").fetchone())
    c.close()
    print("%s  http=%s in=%s out=%s cost=$%.6f" % (
        p.split("/")[-2], r["physical_attempts"], r["tokens_in"], r["tokens_out"], r["spent_cost"]))
    g_http += r["physical_attempts"]; g_in += r["tokens_in"]; g_out += r["tokens_out"]; g_cost += r["spent_cost"]
print("SUBTOTAL http=%d in=%d out=%d cost=$%.6f" % (g_http, g_in, g_out, g_cost))

# 2) episode JSONs inside gated runs
print("\n=== B. episode JSONs (gated) ===")
ep_in = ep_out = ep_calls = 0
for pat in ("results/pilot1_live_run/pilot1_episode.json",
            "results/stage1_feasibility/episodes/*.json",
            "results/stage1_6/episodes/*.json",
            "results/stage1_8/episodes/*.json"):
    for f in ROOT.glob(pat):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ep_in += int(e.get("tokens_in") or 0)
        ep_out += int(e.get("tokens_out") or 0)
        ep_calls += int(e.get("llm_call_count") or e.get("api_calls") or 0)
print("episodes tokens_in=%d tokens_out=%d llm_calls=%d" % (ep_in, ep_out, ep_calls))

# 3) historical real-API artifacts OUTSIDE the 4 ledgers
print("\n=== C. pre-gate real-DeepSeek artifacts (not in BudgetDB) ===")
hist_calls = hist_in = 0
for f in (ROOT / "results/native_alfworld").rglob("*.json"):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    # look for episode-like dicts
    for key in ("llm_call_count", "api_calls", "total_llm_calls"):
        if key in d:
            hist_calls += int(d[key] or 0)
            break
    for key in ("tokens_in", "total_tokens_in", "prompt_tokens"):
        if key in d:
            hist_in += int(d[key] or 0)
            break
    # nested episodes list
    for ep in (d.get("episodes") or []):
        if isinstance(ep, dict):
            hist_calls += int(ep.get("llm_call_count") or ep.get("api_calls") or 0)
            hist_in += int(ep.get("tokens_in") or 0)
print("historical files: llm_calls~%d tokens_in~%d" % (hist_calls, hist_in))

# 4) bill-side from user screenshot
bill_in = 637696 + 9121 + 3809919 + 8427987 + 3472640
bill_out = 68 + 144648 + 69561
bill_req = 68 + 120
print("\n=== D. bill screenshot sums (partial page) ===")
print("bill input_cache tokens=%d  output_total=%d  request_count~%d" % (bill_in, bill_out, bill_req))
print("bill total CNY (from prev screenshot) ≈ 23.33")

print("\n=== E. gap ===")
print("input gap: bill %d vs ledger %d  => x%.1f" % (bill_in, g_in, bill_in / max(1, g_in)))
print("output gap: bill %d vs ledger %d => x%.1f" % (bill_out, g_out, bill_out / max(1, g_out)))
