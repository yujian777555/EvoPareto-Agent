# AFlow Full-text Analysis (arXiv 2410.10762)

**Method sections read via arXiv abstract page + official code. Full PDF
section-by-section = FULL_TEXT_NOT_VERIFIED this session (no PDF parse).**

| Section | Status |
|---|---|
| Abstract | verified (arXiv API/page) |
| Method / Algorithm | inferred from official code + abstract |
| Experiments | abstract claims 6 benchmarks, +5.7% avg |
| Ablation / Limitations | FULL_TEXT_NOT_VERIFIED |

## 15 comparison answers (code-grounded)

1. **Search object:** workflow = Python code + prompt (Operator composition).
2. **Encoding:** `graph.py` class + `prompt.py` strings, round dirs.
3. **Mutation:** LLM-generated `modification/graph/prompt` (GraphOptimize).
4. **New candidates:** LLM rewrite of parent workflow, filtered by
   `check_modification`.
5. **Parent selection:** mixed softmax(α=0.2)+uniform(λ=0.3) over top-k rounds.
6. **Evaluation:** avg score on `validation_rounds` sample of dataset.
7. **Failure traces:** experience.json success/failure lists per father node.
8. **History:** `processed_experience.json`; formatted into optimize prompt.
9. **Rejection:** exact-duplicate modification rejected (`check_modification`).
10. **Overfitting:** validation rounds only; no explicit test-gate in search.
11. **Operator interaction:** not studied in code.
12. **Diagnosis impact:** not studied — modification is opaque text.
13. **Cross-task:** separate workspaces per benchmark.
14. **Solved:** automatic workflow+prompt search with experience memory.
15. **Unsolved:** why a modification works; invalid/duplicate generation rate;
    no real trace artifacts shipped for analysis.
