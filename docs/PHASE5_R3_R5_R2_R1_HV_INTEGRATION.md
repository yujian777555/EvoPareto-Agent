# R2-R1 — HV Integration

`hv_unified.hv_for_objectives(rows, objective_version=...)`:

- `candidate_2obj` → `hypervolume_2d_mixed` with **fixed** ref default `(0, 1.0)`
- `legacy_5obj` → legacy MC hypervolume (unchanged)

Wired into `MemoryEvolutionLoop.current_hypervolume()` and `_record_history()`.

**Golden case 0.115 preserved.** All 2D formal stats share this entrypoint.
