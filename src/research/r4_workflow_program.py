"""R4 workflow-program representation and parent adapter (zero model calls).

Scope
-----
R4 groups D/E need a *mutable* workflow representation whose candidates can
still be executed through the same contract R3 used:

    run_workflow_code_isolated(graph_src, problem=..., llm=IPC(), extra_modules=...)

That contract is: a Python module exposing ``class Workflow`` whose
``async __call__(problem)`` returns either a plain answer or ``(answer, cost)``.

Existing genome types in this repo do NOT satisfy that contract:

* ``src/research/fceol/workflow_genome.WorkflowGenome`` is executed by
  ``fceol.offline_evaluator`` on toy task suites. Nodes are GENERATE/VERIFY/...
  No Docker, no DeepSeek IPC, no AFlow ``operator.Custom``.
* ``src/agent/genome.AgentGenome`` is a categorical agent *configuration*
  vector (planner/memory/reflection/tool/budget). It is not a workflow graph.

Converting the frozen AFlow Parent into either genome would silently change
execution semantics. This module therefore defines a purpose-built
``WorkflowProgram`` that:

1. loads the frozen Parent graph/prompt with hash protection,
2. compiles to R3-compatible graph source (identity when unmutated),
3. supports clone-and-mutate with lineage (for D: flat from Parent; for E:
   gen-2 from gen-1 winner),
4. never touches the network.

Mock evaluation helpers in tests must be tagged SIMULATED and must not write
into ``results/`` real experiment namespaces.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "WorkflowProgram",
    "ParentLoadError",
    "MutationError",
    "load_frozen_parent",
    "mutate_insert_instruction",
    "mutate_add_sampling",
    "mutate_add_check_stage",
    "mutate_single_edit",
    "MUTATION_OPERATORS",
    "generate_flat_candidates",
    "generate_two_generation_candidates",
    "compile_graph_source",
    "validate_graph_source",
    "parent_identity_roundtrip_ok",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ParentLoadError(RuntimeError):
    """Frozen parent artefacts missing, hash-mismatched, or unparseable."""


class MutationError(ValueError):
    """A mutation would produce an invalid or non-representable program."""


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

@dataclass
class WorkflowProgram:
    """Mutable workflow candidate with lineage metadata.

    ``graph_source`` is the executable Python module text (R3 contract).
    ``instruction`` is the prompt text bound as ``INSTRUCTION`` via the
    SERIALISED_INSTRUCTION_REPR contract (may be empty for Parent).
    ``call_style`` records how model calls are made: ``aflow_custom`` (Parent)
    or ``direct_llm`` (Child-style). Mutations may only change style when the
    mutation operator explicitly rebuilds the source.
    """

    program_id: str
    graph_source: str
    instruction: str
    call_style: str  # "aflow_custom" | "direct_llm"
    n_samples: int = 1
    aggregation: str = "none"  # none | majority_vote
    check_on_split_vote: bool = False
    generation: int = 0
    parent_program_id: Optional[str] = None
    operator_history: List[str] = field(default_factory=list)

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
        }


def _new_id() -> str:
    return "wfp-" + uuid.uuid4().hex[:12]


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------------------
# Validation of graph source (R3 contract)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Frozen parent loading (hash-protected)
# ---------------------------------------------------------------------------

# Canonical digests from freeze_manifest.json / BASELINE_AUDIT.md
PARENT_GRAPH_BYTE_SHA256 = "ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e"
PARENT_GRAPH_LF_SHA256 = "a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe"
PARENT_PROMPT_RAW_SHA256 = "34b149ab37e571def0875faeac171867c3a2bb9fff03db4bc0ccca034e48e979"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_frozen_parent(frozen_dir: Path | str) -> WorkflowProgram:
    """Load Parent from ``results/level3_pilot_r2/frozen_candidates`` with hash gates.

    Raises ParentLoadError if bytes do not match the recorded digests or the
    graph is not a valid R3 Workflow module. Does not mutate anything on disk.
    """
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
        # prompt file is tiny; still enforce
        raise ParentLoadError(f"PARENT_PROMPT_SHA_MISMATCH:{p_byte}")

    graph_src = _lf(gbytes.decode("utf-8"))
    err = validate_graph_source(graph_src)
    if err:
        raise ParentLoadError(f"PARENT_GRAPH_INVALID:{err}")

    # Parent execution contract (from parent_graph.py):
    #   one Custom(input=problem, instruction="") call; return (response, cost)
    instruction = ""
    return WorkflowProgram(
        program_id="parent-frozen-0001",
        graph_source=graph_src,
        instruction=instruction,
        call_style="aflow_custom",
        n_samples=1,
        aggregation="none",
        check_on_split_vote=False,
        generation=0,
        parent_program_id=None,
        operator_history=["ROOT_PARENT"],
    )


def parent_identity_roundtrip_ok(program: WorkflowProgram, frozen_dir: Path | str) -> bool:
    """True if program still compiles to the frozen Parent source (LF form)."""
    d = Path(frozen_dir)
    expected = _lf((d / "parent_graph.py").read_bytes().decode("utf-8"))
    return _lf(program.graph_source) == expected and program.instruction == ""


# ---------------------------------------------------------------------------
# Compile / validate
# ---------------------------------------------------------------------------

def compile_graph_source(program: WorkflowProgram) -> str:
    """Graph source for run_workflow_code_isolated.

    Identity for unmutated Parent (exact LF-normalised frozen source). Mutated
    programs already carry their executable source; this function only
    normalises newlines and re-validates.
    """
    src = _lf(program.graph_source)
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return src


# ---------------------------------------------------------------------------
# Mutation operators (clone-and-edit; syntactic; no model calls)
# ---------------------------------------------------------------------------

def _child_of(parent: WorkflowProgram, operator: str, **updates: Any) -> WorkflowProgram:
    updates.setdefault("generation", parent.generation + 1 if operator != "ROOT_PARENT" else parent.generation)
    if operator != "ROOT_PARENT":
        updates.setdefault("parent_program_id", parent.program_id)
        updates.setdefault("generation", parent.generation + 1)
        hist = list(parent.operator_history) + [operator]
        updates.setdefault("operator_history", hist)
    return parent.clone_with(**updates)


def mutate_insert_instruction(parent: WorkflowProgram, *, instruction: str) -> WorkflowProgram:
    """Set a non-empty instruction and bind it the way Parent binds INSTRUCTION.

    Parent AFlow Custom uses ``instruction=""``. This mutation replaces that
    literal with the new instruction text (repr-safe) while keeping the single
    Custom call — semantics change is *the intended mutation* (prompt change).
    """
    if not instruction or not isinstance(instruction, str):
        raise MutationError("INSTRUCTION_EMPTY")
    src = _lf(parent.graph_source)
    # Replace the first instruction=<literal> argument (empty or not) so the
    # operator can also mutate an already-edited child (Group E gen-2).
    pattern = re.compile(r'instruction\s*=\s*(?:"[^"]*"|\'[^\']*\')')
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
    """Record majority-vote sampling; rebuild source as direct-llm multi-sample.

    This is the Group B-style structural change: k independent calls + vote.
    Only valid for a single-call parent-style program.
    """
    if n_samples < 2 or n_samples > 8:
        raise MutationError("N_SAMPLES_OUT_OF_RANGE")
    if parent.n_samples != 1 or parent.aggregation != "none":
        raise MutationError("SAMPLING_REQUIRES_SINGLE_CALL_BASE")
    # Rebuild a Child-style Workflow that takes ``llm`` like frozen child_graph.
    # Keep instruction as solve prefix if set, else default text.
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
        "        best = max(set(votes), key=votes.count)\n"
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
    """Add a tie-break check pass to a sampling program (Child-style)."""
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
        "        best = max(set(votes), key=votes.count)\n"
        "        if votes.count(best) >= 2:\n"
        "            return best\n"
        "        final = await self.llm(f\"{self.check}\\nProblem: {problem}\\nCandidate: {drafts[0]}\")\n"
        "        return final.strip().split(\"Answer:\")[-1].strip()\n"
    )
    err = validate_graph_source(src)
    if err:
        raise MutationError(err)
    return _child_of(parent, "M_ADD_CHECK_STAGE", graph_source=src, check_on_split_vote=True)


def mutate_single_edit(parent: WorkflowProgram, *, old: str, new: str, operator: str = "M_SINGLE_EDIT") -> WorkflowProgram:
    """Replace one literal occurrence in the graph source (syntactic)."""
    if not old:
        raise MutationError("EDIT_EMPTY_OLD")
    src = _lf(parent.graph_source)
    if old not in src:
        raise MutationError("EDIT_TARGET_NOT_FOUND")
    new_src = src.replace(old, new, 1)
    err = validate_graph_source(new_src)
    if err:
        raise MutationError(err)
    return _child_of(parent, operator, graph_source=new_src)


MUTATION_OPERATORS = (
    "M_SET_INSTRUCTION",
    "M_ADD_SAMPLING",
    "M_ADD_CHECK_STAGE",
    "M_SINGLE_EDIT",
)


# ---------------------------------------------------------------------------
# Lineage: Group D (flat) vs Group E (two-generation)
# ---------------------------------------------------------------------------

def generate_flat_candidates(
    parent: WorkflowProgram,
    *,
    n_candidates: int = 4,
    mutator: Callable[[WorkflowProgram, int], WorkflowProgram],
) -> List[WorkflowProgram]:
    """Group D: every candidate mutates the *same* frozen Parent (flat).

    ``mutator(parent, index)`` must return a child of ``parent`` (its
    ``parent_program_id`` must equal ``parent.program_id``). Failures are
    retained as explicit failed records by the caller; this function does not
    silently drop a requested index — if mutator raises, a
    ``_FAILED`` placeholder is not invented; the error propagates so the
    experiment layer can score dev=0 and retain the slot.
    """
    if n_candidates < 1:
        raise MutationError("N_CANDIDATES_INVALID")
    out: List[WorkflowProgram] = []
    for i in range(n_candidates):
        child = mutator(parent, i)
        if child.parent_program_id != parent.program_id:
            raise MutationError(f"LINEAGE_FLAT_VIOLATION:index={i}")
        if child.generation != parent.generation + 1:
            raise MutationError(f"LINEAGE_GEN_VIOLATION:index={i}")
        out.append(child)
    return out


def generate_two_generation_candidates(
    parent: WorkflowProgram,
    *,
    mutator: Callable[[WorkflowProgram, int], WorkflowProgram],
    winner_picker: Callable[[Sequence[WorkflowProgram]], WorkflowProgram],
) -> Tuple[List[WorkflowProgram], WorkflowProgram, List[WorkflowProgram]]:
    """Group E: gen1 (2 from Parent) → winner → gen2 (2 from winner).

    Returns ``(gen1, winner, gen2)``. All four are evaluated later on the same
    dev set; final selection is among all four. The winner's parent_program_id
    must be ``parent.program_id``; each gen-2 child's parent_program_id must be
    the winner's program_id.
    """
    g1 = [mutator(parent, 0), mutator(parent, 1)]
    for ch in g1:
        if ch.parent_program_id != parent.program_id:
            raise MutationError("LINEAGE_GEN1_NOT_FROM_PARENT")
    winner = winner_picker(g1)
    if winner.program_id not in {c.program_id for c in g1}:
        raise MutationError("WINNER_NOT_IN_GEN1")
    g2 = [mutator(winner, 2), mutator(winner, 3)]
    for ch in g2:
        if ch.parent_program_id != winner.program_id:
            raise MutationError("LINEAGE_GEN2_NOT_FROM_WINNER")
        if ch.generation != winner.generation + 1:
            raise MutationError("LINEAGE_GEN2_GEN_VIOLATION")
    return g1, winner, g2

