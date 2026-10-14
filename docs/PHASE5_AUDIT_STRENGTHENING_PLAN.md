# Phase 5-Audit & Strengthening Plan

## Goal

Before paper writing, perform a reviewer-style audit and strengthen the evidence for EvoPareto-Agent.

The goal is not to change NSGA-III / PEEM / PPEC definitions to improve numbers. The goal is to verify correctness, remove hidden leakage, and improve scientific validity.

## Audit Tasks

### 1. Cache Leakage Audit (Priority: P0)

Verify evaluation cache isolation.

Required checks:
- cache key must include task identity
- genome/configuration identity
- benchmark identity
- seed
- backend/model identity
- preference setting when applicable

Add tests proving different experiments cannot reuse incompatible results.

---

### 2. PEEM Causal Attribution Audit (Priority: P0)

Current PEEM learns mutation utility from observed offspring outcomes.

Investigate whether credit represents:
- mutation operator contribution
or only:
- successful offspring correlation

Add analysis:
- parent-controlled comparison
- mutation operator counterfactual evaluation if feasible
- operator utility confidence intervals

Document limitations if full causality is not possible.

---

### 3. Transfer Experiment (Priority: P1)

Validate whether evolutionary experience can transfer.

Experiment:

Train PEEM memory on benchmark A.
Test on benchmark B.

Compare:
- random mutation
- fresh PEEM
- transferred PEEM memory

Main question:

Does PEEM learn reusable search knowledge?

---

### 4. Genotype Evolution Analysis (Priority: P1)

Add visualization and analysis:

- mutation trajectory
- genotype frequency changes
- lineage survival
- Pareto front evolution

Demonstrate that the system learns behavioral configurations rather than simple hyperparameter tuning.

---

### 5. Experimental Difficulty Audit (Priority: P1)

Review all benchmarks for saturation.

Avoid tasks where ReAct already reaches 100% success.

Add harder settings:
- longer horizon
- noisy tools
- constrained budget
- partial observability

---

## Paper Positioning Update

Preferred positioning:

Evolutionary learning of adaptive agent search strategies.

Avoid framing as only:

agent configuration optimization.

The key contribution should be:

PEEM learns reusable evolutionary search experience, while PPEC enables preference-directed Pareto adaptation.

---

## Acceptance Criteria

Before Phase 5 Paper Package:

- cache leakage ruled out
- PEEM attribution analyzed
- transfer experiment completed
- genotype evolution figures generated
- benchmark difficulty reviewed

Only after these checks proceed to final LaTeX package.
