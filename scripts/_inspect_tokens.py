import json
from pathlib import Path

# inspect one real episode's call journal vs summary
for p in [
    "results/stage1_8/episodes/t0_current.json",
    "results/stage1_6/episodes/t0_current_r1.json",
    "results/stage1_feasibility/episodes/t0_G1_s11.json",
]:
    f = Path(p)
    if not f.exists():
        continue
    e = json.loads(f.read_text(encoding="utf-8"))
    print("====", p)
    print(" summary tokens_in/out:", e.get("tokens_in"), e.get("tokens_out"), "llm_calls:", e.get("llm_call_count"))
    cu = e.get("call_usage_journal") or []
    jin = sum(x.get("tokens_in", 0) for x in cu)
    jout = sum(x.get("tokens_out", 0) for x in cu)
    print(" journal n=%d sum_in=%d sum_out=%d" % (len(cu), jin, jout))
    if cu:
        print(" sample journal rows:", cu[:3])
    # decision logs
    dl = e.get("decision_logs") or []
    din = sum(x.get("tokens_in", 0) for x in dl)
    print(" decision_logs n=%d sum_in=%d" % (len(dl), din))
    # trajectory steps vs calls
    print(" traj steps:", len(e.get("trajectory") or []))
