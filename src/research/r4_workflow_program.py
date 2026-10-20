"""R4 workflow-program representation, parent adapter, and experiment protocol.

Zero model calls. Candidates execute through the same contract R3 used
(``run_workflow_code_isolated``): a Python module with ``class Workflow`` whose
``async __call__(problem)`` returns ``answer`` or ``(answer, cost)``.

This module also holds the experiment protocol pieces required by review:

* fixed mutation plan (operators, parameters, RNG seeds, selector)
* Group D / Group E generation with lineage checks
* development-set selection with preregistered tie order
* failed-candidate slot retention (score 0, never dropped)
* no-op mutation rejection
* deterministic majority-vote ties (no ``set`` iteration order)
* Group C = Parent single call + one fixed verification (separate from
  ``M_ADD_CHECK_STAGE``, which is a sampling-path mutation)
* local mock execution of compiled programs (SIMULATED; no Docker, no HTTP)

WorkflowGenome / AgentGenome remain NOT the right representation (different
execution engines). See PREREGISTRATION.md.
"""
from __future__ import annotations

import ast
import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "WorkflowProgram",
    "FailedCandidate",
    "MutationPlan",
    "ParentLoadError",
    "MutationError",
    "load_frozen_parent",
    "mutate_insert_instruction",
    "mutate_add_sampling",
    "mutate_add_check_stage",
    "mutate_single_edit",
    "build_group_c_fixed_verify",
    "MUTATION_OPERATORS",
    "default_mutation_plan",
    "apply_mutation",
    "generate_flat_candidates",
    "generate_two_generation_candidates",
    "select_by_dev_accuracy",
    "select_e_final",
    "compile_graph_source",
    "validate_graph_source",
    "parent_identity_roundtrip_ok",
    "program_provenance",
    "execute_program_locally",
    "extract_answer_text",
    "majority_vote_deterministic",
]


class ParentLoadError(RuntimeError):
    """Frozen parent artefacts missing, hash-mismatched, or unparseable."""


class MutationError(ValueError):
    """A mutation would produce an invalid, empty, or non-representable program."""


def majority_vote_deterministic(votes: Sequence[str]) -> str:
    """Majority vote with first-occurrence tie-break.

    Never uses ``max(set(...))`` — that depends on hash randomization.
    """
    if not votes:
        raise ValueError("EMPTY_VOTES")
    counts: Dict[str, int] = {}
    for v in votes:
        counts[v] = counts.get(v, 0) + 1
    best_n = max(counts.values())
    for v in votes:
        if counts[v] == best_n:
            return v
    raise RuntimeError("UNREACHABLE")


@dataclass
class WorkflowProgram:
    """Mutable workflow candidate with lineage metadata."""

    program_id: str
    graph_source: str
    instruction: str
    call_style: str  # "aflow_custom" | "direct_llm" | "aflow_custom_verify"
    n_samples: int = 1
    aggregation: str = "none"
    check_on_split_vote: bool = False
    fixed_verify: bool = False
    generation: int = 0
    parent_program_id: Optional[str] = None
    operator_history: List[str] = field(default_factory=list)
    failed: bool = False
    failure_reason: Optional[str] = None

    def clone_with(self, **updates: Any) -> "WorkflowProgram":
        base = asdict(self)
        base.update(updates)
        if "program_id" not in updates:
            base["program_id"] = _new_id()
        if "operator_history" not in updates:
            base["operator_history"] = list(self.operator_history)
        return WorkflowProgram(**base)

    def lineage(self) -> Dict[str, Any]:
        return {
            "program_id": self.program_id,
            "parent_program_id": self.parent_program_id,
            "generation": self.generation,
            "operator_history": list(self.operator_history),
            "call_style": self.call_style,
            "n_samples": self.n_samples,
            "aggregation": self.aggregation,
            "check_on_split_vote": self.check_on_split_vote,
            "fixed_verify": self.fixed_verify,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
        }


@dataclass
class FailedCandidate:
    """A candidate slot that could not be produced. Never dropped; dev=0."""

    slot: int
    operator: str
    reason: str
    parent_program_id: Optional[str]
    generation: int

    @property
    def dev_accuracy(self) -> float:
        return 0.0


def _new_id() -> str:
    return "wfp-" + uuid.uuid4().hex[:12]


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def program_provenance(program: WorkflowProgram) -> Dict[str, Any]:
    src = _lf(program.graph_source)
    return {
        "program_id": program.program_id,
        "graph_sha256": hashlib.sha256(src.encode("utf-8")).hexdigest(),
        "instruction_sha256": hashlib.sha256(program.instruction.encode("utf-8")).hexdigest(),
        "call_style": program.call_style,
        "n_samples": program.n_samples,
        "aggregation": program.aggregation,
        "fixed_verify": program.fixed_verify,
        "lineage": program.lineage(),
    }


def validate_graph_source(src: str) -> str:
    """Return '' if src is a plausible R3 Workflow module, else an error code."""
    if not src or not src.strip():
        return "GRAPH_EMPTY"
    text = _lf(src)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return f"GRAPH_SYNTAX_ERROR:{exc.lineno}"
    has_workflow_class = False
    has_async_call = False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Workflow":
            has_workflow_class = True
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "__call__":
                    has_async_call = True
    if not has_workflow_class:
        return "GRAPH_MISSING_WORKFLOW_CLASS"
    if not has_async_call:
        return "GRAPH_MISSING_ASYNC_CALL"
    return ""


PARENT_GRAPH_BYTE_SHA256 = "ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e"
PARENT_GRAPH_LF_SHA256 = "a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe"
PARENT_PROMPT_RAW_SHA256 = "34b149ab37e571def0875faeac171867c3a2bb9fff03db4bc0ccca034e48e979"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_frozen_parent(frozen_dir: Path | str) -> WorkflowProgram:
    """Load Parent from frozen_candidates with SHA gates. No disk mutation."""
    d = Path(frozen_dir)
    gpath = d / "parent_graph.py"
    ppath = d / "parent_prompt.py"
    if not gpath.exists() or not ppath.exists():
        raise ParentLoadError(f"FROZEN_PARENT_FILES_MISSING:{d}")
    gbytes = gpath.read_bytes()
    pbytes = ppath.read_bytes()
    g_byte = _sha256_bytes(gbytes)
    g_lf = _sha256_bytes(gbytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    p_byte = _sha256_bytes(pbytes)
    if g_byte != PARENT_GRAPH_BYTE_SHA256 and g_lf != PARENT_GRAPH_LF_SHA256:
        raise ParentLoadError(f"PARENT_GRAPH_SHA_MISMATCH:byte={g_byte} lf={g_lf}")
    if p_byte != PARENT_PROMPT_RAW_SHA256:
        raise ParentLoadError(f"PARENT_PROMPT_SHA_MISMATCH:{p_byte}")

    graph_src = _lf(gbytes.decode("utf-8"))
    err = validate_graph_source(graph_src)
    if err:
        raise ParentLoadError(f"PARENT_GRAPH_INVALID:{err}")

    return WorkflowProgram(
        program_id="parent-frozen-0001",
        graph_source=graph_src,
        instruction="",
        call_style="aflow_custom",
        n_samples=1,
        aggregation="none",
        check_on_split_vote=False,
        fixed_verify=False,
        generation=0,
        parent_program_id=None,
        operator_history=["ROOT_PARENT"],
    )


def parent_identity_roundtrip_ok(program: WorkflowProgram, frozen_dir: Path | str) -> bool:
    d = Path(frozen_dir)
    expected = _lf((d / "parent_graph.py").read_bytes().decode("utf-8"))
    return _lf(program.graph_source) == expected and program.instruction == ""


def compile_graph_source(program: WorkflowProgram) -> str:
    src = _lf(program.graph_source)
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return src


# ---------------------------------------------------------------------------
# Mutation operators
# ---------------------------------------------------------------------------

def _child_of(parent: WorkflowProgram, operator: str, **updates: Any) -> WorkflowProgram:
    updates.setdefault("parent_program_id", parent.program_id)
    updates.setdefault("generation", parent.generation + 1)
    hist = list(parent.operator_history) + [operator]
    updates.setdefault("operator_history", hist)
    return parent.clone_with(**updates)


def mutate_insert_instruction(parent: WorkflowProgram, *, instruction: str) -> WorkflowProgram:
    """Replace instruction=<literal>. Rejects empty and no-op rewrites."""
    if not isinstance(instruction, str):
        raise MutationError("INSTRUCTION_EMPTY")
    if instruction == parent.instruction:
        raise MutationError("NOOP_MUTATION")
    if not instruction:
        raise MutationError("INSTRUCTION_EMPTY")
    src = _lf(parent.graph_source)
    pattern = re.compile(r"instruction\s*=\s*(?:\"[^\"]*\"|'[^']*')")
    if not pattern.search(src):
        raise MutationError("PARENT_INSTRUCTION_SLOT_NOT_FOUND")
    new_src, nsub = pattern.subn("instruction=" + repr(instruction), src, count=1)
    if nsub != 1 or new_src == src:
        raise MutationError("INSTRUCTION_REWRITE_NOOP")
    err = validate_graph_source(new_src)
    if err:
        raise MutationError(err)
    return _child_of(parent, "M_SET_INSTRUCTION", graph_source=new_src, instruction=instruction)


def mutate_add_sampling(parent: WorkflowProgram, *, n_samples: int) -> WorkflowProgram:
    """Group B-style: k samples + deterministic majority vote."""
    if n_samples < 2 or n_samples > 8:
        raise MutationError("N_SAMPLES_OUT_OF_RANGE")
    if parent.n_samples != 1 or parent.aggregation != "none":
        raise MutationError("SAMPLING_REQUIRES_SINGLE_CALL_BASE")
    if parent.fixed_verify:
        raise MutationError("SAMPLING_REQUIRES_NON_VERIFY_BASE")
    solve = parent.instruction or "Solve step by step, end with 'Answer: <num>'."
    src = (
        "class Workflow:\n"
        "    def __init__(self, llm):\n"
        "        self.llm = llm\n"
        "        self.solve = " + repr(solve) + "\n"
        "\n"
        "    async def __call__(self, problem):\n"
        "        import asyncio\n"
        "        drafts = await asyncio.gather(*[\n"
        "            self.llm(f\"{self.solve}\\n{problem}\")\n"
        "            for _ in range(" + str(int(n_samples)) + ")\n"
        "        ])\n"
        "        votes = [d.strip().split(\"Answer:\")[-1].strip() for d in drafts]\n"
        "        counts = {}\n"
        "        for v in votes:\n"
        "            counts[v] = counts.get(v, 0) + 1\n"
        "        best_n = max(counts.values())\n"
        "        best = next(v for v in votes if counts[v] == best_n)\n"
        "        return best\n"
    )
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return _child_of(
        parent,
        "M_ADD_SAMPLING",
        graph_source=src,
        call_style="direct_llm",
        n_samples=int(n_samples),
        aggregation="majority_vote",
    )


def mutate_add_check_stage(parent: WorkflowProgram) -> WorkflowProgram:
    """Sampling-path mutation. NOT Group C (see build_group_c_fixed_verify)."""
    if parent.aggregation != "majority_vote":
        raise MutationError("CHECK_REQUIRES_MAJORITY_VOTE")
    solve = parent.instruction or "Solve step by step, end with 'Answer: <num>'."
    src = (
        "class Workflow:\n"
        "    def __init__(self, llm):\n"
        "        self.llm = llm\n"
        "        self.solve = " + repr(solve) + "\n"
        "        self.check = \"Recompute and confirm or correct; end with 'Answer: <num>'.\"\n"
        "\n"
        "    async def __call__(self, problem):\n"
        "        import asyncio\n"
        "        drafts = await asyncio.gather(*[\n"
        "            self.llm(f\"{self.solve}\\n{problem}\")\n"
        "            for _ in range(" + str(int(parent.n_samples)) + ")\n"
        "        ])\n"
        "        votes = [d.strip().split(\"Answer:\")[-1].strip() for d in drafts]\n"
        "        counts = {}\n"
        "        for v in votes:\n"
        "            counts[v] = counts.get(v, 0) + 1\n"
        "        best_n = max(counts.values())\n"
        "        best = next(v for v in votes if counts[v] == best_n)\n"
        "        if counts[best] >= 2:\n"
        "            return best\n"
        "        final = await self.llm(f\"{self.check}\\nProblem: {problem}\\nCandidate: {drafts[0]}\")\n"
        "        return final.strip().split(\"Answer:\")[-1].strip()\n"
    )
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return _child_of(parent, "M_ADD_CHECK_STAGE", graph_source=src, check_on_split_vote=True)


def mutate_single_edit(
    parent: WorkflowProgram, *, old: str, new: str, operator: str = "M_SINGLE_EDIT"
) -> WorkflowProgram:
    if not old:
        raise MutationError("EDIT_EMPTY_OLD")
    if old == new:
        raise MutationError("NOOP_MUTATION")
    src = _lf(parent.graph_source)
    if old not in src:
        raise MutationError("EDIT_TARGET_NOT_FOUND")
    new_src = src.replace(old, new, 1)
    if new_src == src:
        raise MutationError("NOOP_MUTATION")
    err = validate_graph_source(new_src)
    if err:
        raise MutationError(err)
    return _child_of(parent, operator, graph_source=new_src)


# ---------------------------------------------------------------------------
# Group C — Parent single call + ONE fixed verification (not sampling)
# ---------------------------------------------------------------------------

GROUP_C_CHECK_INSTRUCTION = "Recompute the arithmetic and output the final number only."


def build_group_c_fixed_verify(parent: WorkflowProgram) -> WorkflowProgram:
    """Group C operational definition: Parent call, then one fixed verify.

    Stage 1: single call with parent instruction.
    Stage 2: one verification prompt with the FIXED checker instruction.
    Scoring uses the checker output. Calls per task = 2. No sampling.
    Independent of mutate_add_check_stage.
    """
    if parent.call_style != "aflow_custom":
        raise MutationError("GROUP_C_REQUIRES_PARENT_STYLE")
    if parent.aggregation != "none" or parent.n_samples != 1:
        raise MutationError("GROUP_C_REQUIRES_SINGLE_CALL_PARENT")
    if parent.fixed_verify:
        raise MutationError("GROUP_C_ALREADY_FIXED_VERIFY")
    src = (
        "class Workflow:\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        self.llm = kwargs.get('llm') or (args[0] if args else None)\n"
        "        self._instr1 = " + repr(parent.instruction) + "\n"
        "        self._instr2 = " + repr(GROUP_C_CHECK_INSTRUCTION) + "\n"
        "\n"
        "    async def __call__(self, problem):\n"
        "        first = self._call_llm(self._instr1, problem)\n"
        "        second = self._call_llm(self._instr2, problem)\n"
        "        return second\n"
        "\n"
        "    def _call_llm(self, instruction, problem):\n"
        "        hook = getattr(self, 'llm', None)\n"
        "        if hook is None:\n"
        "            raise RuntimeError('LLM_NOT_BOUND')\n"
        "        prompt = f'{instruction}\\n{problem}' if instruction else problem\n"
        "        if hasattr(hook, '_request'):\n"
        "            return hook._request(prompt)\n"
        "        return hook(prompt)\n"
    )
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return _child_of(
        parent,
        "GROUP_C_FIXED_VERIFY",
        graph_source=src,
        call_style="aflow_custom_verify",
        instruction=parent.instruction,
        fixed_verify=True,
        n_samples=1,
        aggregation="none",
    )


# ---------------------------------------------------------------------------
# Fixed mutation plan (operators, parameters, seeds, selector)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MutationPlan:
    """Frozen mutation distribution for D/E. Must be recorded in the freeze file."""

    seed: int
    operator_names: Tuple[str, ...]
    operator_probs: Tuple[float, ...]
    instruction_pool: Tuple[str, ...]
    sampling_ks: Tuple[int, ...] = (2, 3, 4)
    allow_noop: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["operator_names"] = list(self.operator_names)
        d["operator_probs"] = list(self.operator_probs)
        d["instruction_pool"] = list(self.instruction_pool)
        d["sampling_ks"] = list(self.sampling_ks)
        return d


def default_mutation_plan(seed: int) -> MutationPlan:
    """Canonical plan: 50% M_SET_INSTRUCTION, 50% M_ADD_SAMPLING.

    M_ADD_CHECK_STAGE / M_SINGLE_EDIT are available but not in the default
    distribution so D and E stay comparable. Changing the plan requires a new
    freeze version.
    """
    return MutationPlan(
        seed=int(seed),
        operator_names=("M_SET_INSTRUCTION", "M_ADD_SAMPLING"),
        operator_probs=(0.5, 0.5),
        instruction_pool=(
            "Solve step by step, end with 'Answer: <num>'.",
            "Think carefully, verify arithmetic, final number after 'Answer:'.",
            "Compute directly. Output the numeric answer after 'Answer:'.",
            "Solve briefly. Final answer after 'Answer:'.",
        ),
        sampling_ks=(2, 3, 4),
        allow_noop=False,
    )


class _SeededRNG:
    """LCG so operator choice is deterministic given (plan.seed, slot)."""

    def __init__(self, seed: int) -> None:
        self.state = int(seed) & 0x7FFFFFFF
        if self.state == 0:
            self.state = 1

    def next_int(self, n: int) -> int:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state % n

    def next_float(self) -> float:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 0xFFFFFFFF


def apply_mutation(
    parent: WorkflowProgram,
    plan: MutationPlan,
    *,
    slot: int,
) -> WorkflowProgram | FailedCandidate:
    """One mutation from the plan. Failed slots become FailedCandidate (dev=0).

    No-op mutations are re-raised unless ``plan.allow_noop`` — they never
    silently become a child candidate.
    """
    rng = _SeededRNG(plan.seed + 10007 * (slot + 1))
    u = rng.next_float()
    acc = 0.0
    op = plan.operator_names[-1]
    for name, p in zip(plan.operator_names, plan.operator_probs):
        acc += p
        if u <= acc:
            op = name
            break
    try:
        if op == "M_SET_INSTRUCTION":
            instr = plan.instruction_pool[rng.next_int(len(plan.instruction_pool))]
            return mutate_insert_instruction(parent, instruction=instr)
        if op == "M_ADD_SAMPLING":
            k = plan.sampling_ks[rng.next_int(len(plan.sampling_ks))]
            return mutate_add_sampling(parent, n_samples=k)
        if op == "M_ADD_CHECK_STAGE":
            return mutate_add_check_stage(parent)
        raise MutationError(f"UNKNOWN_OPERATOR:{op}")
    except MutationError as exc:
        reason = str(exc.args[0]) if exc.args else type(exc).__name__
        if not plan.allow_noop and reason == "NOOP_MUTATION":
            raise
        return FailedCandidate(
            slot=slot,
            operator=op,
            reason=reason,
            parent_program_id=parent.program_id,
            generation=parent.generation + 1,
        )


# ---------------------------------------------------------------------------
# Selection protocol (dev accuracy + preregistered tie order)
# ---------------------------------------------------------------------------

def select_by_dev_accuracy(
    candidates: Sequence[WorkflowProgram | FailedCandidate],
    dev_scores: Mapping[str, float],
    *,
    tie_order: Optional[Sequence[str]] = None,
) -> Tuple[int, Any]:
    """Pick (index, candidate) with highest dev accuracy.

    * FailedCandidate always scores 0.0.
    * Ties broken by tie_order (program_id list), else by input index.
    * Missing scores on non-failed programs raise — never silently 0.
    """
    if not candidates:
        raise ValueError("EMPTY_CANDIDATES")
    order_index: Dict[str, int] = {}
    if tie_order is not None:
        for i, pid in enumerate(tie_order):
            order_index[pid] = i

    def sort_key(item: Tuple[int, Any]):
        i, cand = item
        if isinstance(cand, FailedCandidate):
            score = 0.0
            pid = "FAILED-%d" % cand.slot
        else:
            if cand.program_id not in dev_scores:
                raise ValueError("MISSING_DEV_SCORE:%s" % cand.program_id)
            score = float(dev_scores[cand.program_id])
            pid = cand.program_id
        tie = order_index.get(pid, i)
        return (-score, tie, i)

    ranked = sorted(enumerate(candidates), key=sort_key)
    return ranked[0]


def select_e_final(
    all_four: Sequence[WorkflowProgram | FailedCandidate],
    dev_scores: Mapping[str, float],
) -> Tuple[int, Any]:
    """E final winner among gen1+gen2 in prereg order e1a < e1b < e2a < e2b."""
    if len(all_four) != 4:
        raise ValueError("E_FINAL_REQUIRES_FOUR_CANDIDATES")
    return select_by_dev_accuracy(all_four, dev_scores)


# ---------------------------------------------------------------------------
# Lineage: Group D (flat) vs Group E (two-generation)
# ---------------------------------------------------------------------------

def generate_flat_candidates(
    parent: WorkflowProgram,
    *,
    n_candidates: int = 4,
    mutator: Callable[[WorkflowProgram, int], WorkflowProgram | FailedCandidate],
) -> List[WorkflowProgram | FailedCandidate]:
    """Group D: all non-failed children from the same frozen Parent.

    Failed slots are kept. Successful children must have
    parent_program_id == parent.program_id and generation == parent.generation+1.
    """
    if n_candidates < 1:
        raise MutationError("N_CANDIDATES_INVALID")
    out: List[WorkflowProgram | FailedCandidate] = []
    for i in range(n_candidates):
        child = mutator(parent, i)
        if isinstance(child, FailedCandidate):
            out.append(child)
            continue
        if child.parent_program_id != parent.program_id:
            raise MutationError("LINEAGE_FLAT_VIOLATION:index=%d" % i)
        if child.generation != parent.generation + 1:
            raise MutationError("LINEAGE_GEN_VIOLATION:index=%d" % i)
        out.append(child)
    return out


def generate_two_generation_candidates(
    parent: WorkflowProgram,
    *,
    mutator: Callable[[WorkflowProgram, int], WorkflowProgram | FailedCandidate],
    dev_scores_gen1: Mapping[str, float] | Callable[[WorkflowProgram], float],
) -> Tuple[
    List[WorkflowProgram | FailedCandidate],
    Any,
    List[WorkflowProgram | FailedCandidate],
]:
    """Group E with built-in gen-1 winner selection.

    1. Two candidates from Parent (slots 0,1); failures kept.
    2. Gen-1 winner via select_by_dev_accuracy on dev_scores_gen1
       (tie order = creation order). If all gen-1 failed, gen-2 slots are
       FailedCandidate — never invent a winner.
    3. Two candidates from the winner (slots 2,3); failures kept; successful
       children must descend from the winner.
    """
    g1 = [mutator(parent, 0), mutator(parent, 1)]
    ok1 = [c for c in g1 if not isinstance(c, FailedCandidate)]
    if not ok1:
        g2 = [
            FailedCandidate(2, "M_GEN2", "GEN1_ALL_FAILED", parent.program_id, parent.generation + 1),
            FailedCandidate(3, "M_GEN2", "GEN1_ALL_FAILED", parent.program_id, parent.generation + 1),
        ]
        winner = FailedCandidate(0, "M_GEN1_WINNER", "GEN1_ALL_FAILED", parent.program_id, parent.generation + 1)
        return g1, winner, g2

    if callable(dev_scores_gen1):
        gen1_scores = {
            c.program_id: float(dev_scores_gen1(c))
            for c in g1
            if not isinstance(c, FailedCandidate)
        }
    else:
        gen1_scores = dev_scores_gen1
    _idx, winner = select_by_dev_accuracy(g1, gen1_scores)
    if isinstance(winner, FailedCandidate):
        g2 = [
            FailedCandidate(2, "M_GEN2", "WINNER_FAILED", parent.program_id, parent.generation + 1),
            FailedCandidate(3, "M_GEN2", "WINNER_FAILED", parent.program_id, parent.generation + 1),
        ]
        return g1, winner, g2

    g2 = []
    for i in (2, 3):
        child = mutator(winner, i)
        if isinstance(child, FailedCandidate):
            g2.append(child)
            continue
        if child.parent_program_id != winner.program_id:
            raise MutationError("LINEAGE_GEN2_NOT_FROM_WINNER")
        if child.generation != winner.generation + 1:
            raise MutationError("LINEAGE_GEN2_GEN_VIOLATION")
        g2.append(child)
    return g1, winner, g2


# ---------------------------------------------------------------------------
# Local mock execution (SIMULATED) — harness contract, not Docker/HTTP
# ---------------------------------------------------------------------------

def extract_answer_text(result: Any) -> str:
    """Mirror run_workflow_code_isolated answer extraction."""
    if isinstance(result, (tuple, list)) and result:
        return str(result[0])
    return str(result)


def execute_program_locally(
    program: WorkflowProgram,
    problem: str,
    *,
    llm_hook: Callable[[str], str],
) -> Dict[str, Any]:
    """Execute a compiled program in-process with a controlled fake model.

    Mirrors construction / call / answer extraction of run_workflow_code_isolated
    WITHOUT Docker or HTTP. SIMULATED evidence that the adapter produces
    runnable programs. Full Docker-path proof still requires an authorized run.
    """
    src = compile_graph_source(program)
    ns: Dict[str, Any] = {"__name__": "r4_candidate"}
    try:
        exec(compile(src, "<r4_candidate>", "exec"), ns)
    except Exception as exc:
        return {
            "ok": False,
            "error": "GRAPH_EXEC:%s:%s" % (type(exc).__name__, exc),
            "answer_text": None,
            "evidence_class": "SIMULATED",
        }

    Workflow = ns.get("Workflow")
    if Workflow is None:
        return {"ok": False, "error": "GRAPH_MISSING_WORKFLOW_CLASS", "answer_text": None, "evidence_class": "SIMULATED"}

    import asyncio

    class _HookLLM:
        """Fake model hook.

        ``_request`` is sync (matches R3 IPC). ``__call__`` returns a coroutine
        so ``asyncio.gather(self.llm(...))`` in sampling graphs works.
        """

        def __init__(self, fn):
            self._fn = fn
            self.calls: List[str] = []

        def _request(self, prompt: str) -> str:
            self.calls.append(prompt)
            return self._fn(prompt)

        async def __call__(self, prompt: str) -> str:
            self.calls.append(prompt)
            return self._fn(prompt)

        def get_usage_summary(self):
            return {"total_cost": 0.0}

    hook = _HookLLM(llm_hook)
    obj = None
    errors = []
    for maker in (
        lambda: Workflow(),
        lambda: Workflow(None),
        lambda: Workflow("w", None, None),
        lambda: Workflow("w", object(), None),
        lambda: Workflow(hook),
    ):
        try:
            obj = maker()
            break
        except TypeError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append("%s:%s" % (type(exc).__name__, exc))
    if obj is None:
        return {
            "ok": False,
            "error": "WORKFLOW_CTOR_FAILED:%s" % errors,
            "answer_text": None,
            "evidence_class": "SIMULATED",
        }

    try:
        if getattr(obj, "llm", None) is None:
            obj.llm = hook
    except Exception:
        pass

    import asyncio

    async def _run():
        return await obj(problem)

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        return {
            "ok": False,
            "error": "WORKFLOW_CALL:%s:%s" % (type(exc).__name__, exc),
            "answer_text": None,
            "n_llm_calls": len(hook.calls),
            "evidence_class": "SIMULATED",
        }

    answer = extract_answer_text(result)
    return {
        "ok": True,
        "answer_text": answer,
        "answer_len": len(answer),
        "n_llm_calls": len(hook.calls),
        "call_style": program.call_style,
        "program_id": program.program_id,
        "evidence_class": "SIMULATED",
    }


MUTATION_OPERATORS = (
    "M_SET_INSTRUCTION",
    "M_ADD_SAMPLING",
    "M_ADD_CHECK_STAGE",
    "M_SINGLE_EDIT",
)
