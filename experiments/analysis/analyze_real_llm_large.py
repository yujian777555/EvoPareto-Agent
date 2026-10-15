"""Phase5-R3 analysis: aggregate large-scale real LLM results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "real_llm_large"


def load(name: str):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> dict:
    alf = load("alfworld.json")
    web = load("webshop.json")
    cost = load("cost_analysis.json")
    summary = load("summary.json")

    print("=== ALFWorld (real DeepSeek) ===")
    for row in alf.get("table", []):
        print(row["Method"],
              "Succ", row["Success"], "HV", row["HV"],
              "IGD", row["IGD"], "Cost", row["Cost"])
    print("=== WebShop (real DeepSeek) ===")
    for row in web.get("table", []):
        print(row["Method"],
              "Succ", row["Success"], "HV", row["HV"],
              "IGD", row["IGD"], "Cost", row["Cost"])
    print("=== Cost ===")
    print(json.dumps({k: cost.get(k) for k in (
        "total_api_calls", "total_tokens", "total_cost_usd",
        "cache_hits", "cache_misses", "within_budget",
    )}, indent=2))

    # Comparison with simulator (Phase5-BM numbers, offline)
    sim = {
        "alfworld_peem_success": 0.883,
        "webshop_peem_success": 0.500,
    }
    real_peem = {}
    for bench, pack in (("alfworld", alf), ("webshop", web)):
        for row in pack.get("table", []):
            if row["Method"] == "B2_nsga3_peem":
                real_peem[bench] = row["Success"]["mean"]
    comparison = {
        "simulator_success": sim,
        "real_llm_peem_success": real_peem,
        "note": "Simulator uses mock LLM; real uses DeepSeek chat completions.",
    }
    (OUT / "simulator_comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("comparison", comparison)
    return {"alfworld": alf, "webshop": web, "cost": cost, "comparison": comparison}


if __name__ == "__main__":
    main()
