# Phase5-R3-R5-R1 — Experiment Preregistration

## Arms

| Arm | Method |
|-----|--------|
| A | Random Search |
| B | **NSGA-II** |
| C | NSGA-III |
| D | NSGA-III + PEEM |
| E | NSGA-III + PEEM + PPEC |
| F (optional) | NSGA-III + PPEC |

## Objectives (frozen candidate)

`F(g) = (SuccessRate ↑, InferenceCost ↓)` version `candidate_2obj`.

## Shared

- deepseek-flash · ALFWorld TextWorld · valid_train · H=30
- equal genome evals & native episodes
- equal physical HTTP + $ gate (SQLite ledger)
- pinned task manifest + seeds

## Primary metrics

SuccessRate · raw Cost · 2D HV (pre-registered ref) · PSS (PPEC only)

## Secondary

API calls · tokens · env steps · wall time · mutation entropy · PEEM utility

## Budget note

Report **equal-evaluation** and **equal-resource** views (HTTP cost differs
across arms when reflection varies).

**Pilot 2 (multi-seed live) requires Planner approval — not run this phase.**
