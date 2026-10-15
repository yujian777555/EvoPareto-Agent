"""Stage E: minimal live smoke (≤20 physical HTTP, $0.10) with persistent ledger."""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/")

from src.backend.base import DeepSeekBackend
from src.runtime.api_budget import APICallGate, BillingBlocked, physical_http_count


def main():
    ledger = "/results/phase5_r3_r5/minimal_live_smoke/budget_ledger.json"
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    backend = DeepSeekBackend(max_retries=1, timeout=25)
    gate = APICallGate(
        backend.generate,
        max_calls=20,
        max_cost_usd=0.10,
        max_retries=1,
        ledger_path=ledger,
    )
    out = {"model": backend.model, "results": []}
    for i in range(2):
        try:
            resp = gate.generate("Reply with exactly: OK", budget=8)
            out["results"].append({
                "i": i,
                "ok": True,
                "text": resp.text[:40],
                "tokens_in": resp.tokens_prompt,
                "tokens_out": resp.tokens_completion,
                "cost": resp.cost,
                "model": resp.model,
            })
        except BillingBlocked as e:
            out["results"].append({"i": i, "ok": False, "error": str(e)[:200]})
            break
        except Exception as e:
            out["results"].append({"i": i, "ok": False, "error": f"{type(e).__name__}:{e}"[:200]})
            break
    out["snapshot"] = gate.snapshot()
    out["physical_http"] = physical_http_count()
    gate.assert_clean_shutdown()
    path = "/results/phase5_r3_r5/minimal_live_smoke/live_smoke.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("WROTE", path)
    print(json.dumps({"snapshot": out["snapshot"], "results": out["results"]}, indent=2)[:800])


if __name__ == "__main__":
    main()
