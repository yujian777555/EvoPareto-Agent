"""End-to-end mock run of AFlow official search loop (0 real LLM).

Runs REAL Optimizer._optimize_graph with MockLLM + MockEvaluator.
Uses official GSM8K round_1 templates as seed. Network: none.
Generated graph code is NOT executed as subprocess.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AFLOW = ROOT / "external" / "AFlow"

# dependency stub (not algorithm change)
try:
    import tree_sitter  # noqa
except Exception:
    ts = types.ModuleType("tree_sitter")
    ts.Node = object
    ts.Parser = object
    ts.Language = object
    sys.modules["tree_sitter"] = ts

CALLS = {"prompts": [], "modifications": [], "scores": [], "selections": []}


class MockLLM:
    def __init__(self, *a, **k):
        self.n = 0

    def get_usage_summary(self):
        return {"total_cost": 0.0}

    async def __call__(self, prompt, **kw):
        self.n += 1
        CALLS["prompts"].append(len(prompt))
        mod = f"mock modification v{self.n}"
        CALLS["modifications"].append(mod)
        return (
            f"<modification>{mod}</modification>\n"
            f"<graph>class Workflow:\n    async def __call__(self, problem):\n        return 'ans', 0.0</graph>\n"
            f"<prompt>INSTRUCTION = 'v{self.n}'</prompt>"
        )

    async def call_with_format(self, prompt, formatter):
        raw = await self(prompt)
        # Optimizer indexes response["modification"] — return structured dict
        # graph/prompt must be valid Python (prompt.py is imported)
        return {
            "modification": f"mock modification v{self.n}",
            "graph": "class Workflow:\n    async def __call__(self, problem):\n        return 'ans', 0.0",
            "prompt": f"INSTRUCTION = 'v{self.n}'",
        }


class MockEvaluator:
    def __init__(self, eval_path=None):
        self.eval_path = eval_path

    async def graph_evaluate(self, dataset, graph, config, directory, is_test=False):
        # deterministic score sequence to observe selection pressure
        seq = [0.50, 0.62, 0.55, 0.70, 0.58, 0.66]
        s = seq[CALLS["scores"].__len__() % len(seq)]
        CALLS["scores"].append(s)
        return s, 0.0, 0.0


def main(argv=None) -> int:
    import argparse, hashlib
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)
    run_id = args.run_id or hashlib.sha256(os.urandom(16)).hexdigest()[:12]

    sys.path.insert(0, str(AFLOW))
    import scripts.optimizer as opt_mod
    import scripts.evaluator as ev_mod
    import scripts.optimizer_utils.evaluation_utils as eu_mod

    opt_mod.create_llm_instance = lambda cfg: MockLLM()
    ev_mod.Evaluator = MockEvaluator
    eu_mod.Evaluator = MockEvaluator

    # Optimizer uses scripts.* — must run with AFlow on sys.path
    from scripts.optimizer import Optimizer

    result = {
        "run_id": run_id,
        "official_search_loop": "NOT_RUN",
        "rounds_completed": 0,
        "selections": [], "modifications": [], "scores": [],
        "experience_files": 0, "results_json_written": False,
        "optimize_prompts_seen": 0,
        "network_isolation": "MockLLM + MockEvaluator",
        "generated_code_executed": False,
    }

    with tempfile.TemporaryDirectory(dir=str(ROOT / "results")) as td:
        td_path = Path(td)
        # Build importable package 'workspace.GSM8K.workflows' from official templates
        ws_src = AFLOW / "workspace" / "GSM8K" / "workflows"
        ws_dst = td_path / "workspace" / "GSM8K" / "workflows"
        shutil.copytree(ws_src, ws_dst)
        for p in (td_path / "workspace").rglob("*"):
            if p.is_dir():
                (p / "__init__.py").touch()
        # empty results.json is invalid JSON → write [] so loaders work
        (ws_dst / "results.json").write_text("[]", encoding="utf-8")
        (ws_dst / "round_1" / "log.json").write_text("{}", encoding="utf-8")

        prev_cwd = os.getcwd()
        os.chdir(td_path)
        sys.path.insert(0, str(td_path))
        try:
            opt = Optimizer(
                dataset="GSM8K",
                question_type="math",
                opt_llm_config={"model": "mock"},
                exec_llm_config={"model": "mock"},
                operators=["Custom", "ScEnsemble", "Programmer"],
                sample=2,
                max_rounds=3,
                validation_rounds=1,
                optimized_path="workspace",
                initial_round=1,
                check_convergence=False,
            )
            orig_select = opt.data_utils.select_round

            def traced_select(items):
                pick = orig_select(items)
                CALLS["selections"].append({"round": pick.get("round"), "score": pick.get("score")})
                return pick

            opt.data_utils.select_round = traced_select

            try:
                opt.optimize(mode="Graph")
                result["official_search_loop"] = "PASS"
            except Exception as e:
                result["official_search_loop"] = f"FAIL: {type(e).__name__}: {e}"

            result["rounds_completed"] = int(opt.round)
            result["selections"] = CALLS["selections"]
            result["modifications"] = CALLS["modifications"]
            result["scores"] = CALLS["scores"]
            result["optimize_prompts_seen"] = len(CALLS["prompts"])
            exp_files = list(Path("workspace").rglob("experience.json"))
            result["experience_files"] = len(exp_files)
            rj = Path("workspace") / "GSM8K" / "workflows" / "results.json"
            result["results_json_written"] = rj.exists() and rj.stat().st_size > 0
            if exp_files:
                try:
                    result["sample_experience"] = json.loads(exp_files[0].read_text(encoding="utf-8"))
                except Exception:
                    pass
        finally:
            os.chdir(prev_cwd)

    print(json.dumps(result, indent=2))
    out = ROOT / "results" / "stage3_0_p1_r1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mock_execution_trace.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result.get("official_search_loop") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
