# Capability Inheritance Correction

Prior metric mixed up fathers/children. Correct lineage: a successful
mutation produces child C at round r; C is "reselected" if round r later
appears as father of other rounds.

| Metric | success children | fail children |
|---|---:|---:|
| n | 41 | 103 |
| reselection rate | **0.707** | 0.097 |
| mean offspring | **2.24** | 0.21 |

Successful children are reselected ~7× more often. This is **observational**;
early rounds have more remaining opportunities (not fully controlled).
**BEHAVIORAL_INHERITANCE_NOT_ESTABLISHED** — code/reselection ≠ capability.

**Verdict: INHERITANCE_PARTIALLY_SUPPORTED** (reselection evidence only).
