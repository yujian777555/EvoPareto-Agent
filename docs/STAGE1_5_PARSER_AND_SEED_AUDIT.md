# Stage 1.5 Parser & Seed Audit

## Parser failure reconciliation (Q5)

Definitions (frozen):

| Symbol | Meaning |
|---|---|
| FIRST_PARSE_FAILURE | decision whose **initial** parse failed (final `parse_ok=False` **or** `reflection_trigger` set) |
| REFLECTION_ATTEMPT | `reflection_trigger` non-empty |
| REFLECTION_RECOVERED | reflection attempted **and** final `parse_ok=True` |
| FINAL_PARSE_FAILURE | final `parse_ok=False` |
| FALLBACK_USED | `used_fallback=True` |

Recomputed from 468 DecisionLog rows (`parser_failure_reconciliation.json`):

| Quantity | Value |
|---|---:|
| total decisions | 468 |
| **FIRST_PARSE_FAILURE** | **10** |
| **REFLECTION_ATTEMPT** | **4** |
| **REFLECTION_RECOVERED** | **4** |
| **FINAL_PARSE_FAILURE** | **6** |
| **FALLBACK_USED** | **6** |

**Parse failure ≠ fallback.** 10 first failures; 4 were repaired by reflection;
6 remained and fell back to `admissible[0]`. Stage 1's earlier "6/468" counted
only finals — the correct first-failure count is **10**.

Parser is still **not** the main loop driver (10/468 ≈ 2.1% first-failure rate).

## Seed semantics (Q6)

| Random source | Controlled by Stage 1 `seed`? |
|---|---|
| Python `random` | No |
| NumPy | Not used |
| PyTorch | Not used |
| ALFWorld reset / game selection | No — `force_game_file` + manifest index |
| Task selection | No — frozen indices |
| Genome mutation | N/A (fixed genomes) |
| **LLM sampling** | **No** — no `seed` field in DeepSeek payload; temperature unset |

**Verdict: `SEED_NOT_EFFECTIVE_FOR_LIVE_POLICY`**

seed=11 vs 23 are **labels**, not controlled RNG replicates. Trajectory
differences come from LLM sampling noise, not from an experimenter-set seed.

### Future protocol recommendation
- Do not treat two seeds as independent statistical replicates.
- Prefer more episodes per cell over pseudo-replicates.
- If a provider seed or temperature is fixed later, apply identically to all
  arms and document it in the run manifest.
