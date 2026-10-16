# Baseline Reproduction Audit

## Candidates

| Baseline | Paper/code | Repro difficulty | Verdict |
|---|---|---|---|
| **AFlow** | 2410.10762 · github.com/FoundationAgents/AFlow | Medium (LLM API + 6 benches) | **PRIMARY** |
| GEPA | baseline in many 2026 papers | Medium | mechanism reference |
| HarnessFix | name only — **REFERENCE_UNVERIFIED** | Unknown | cannot select |
| mini-SWE-agent | used in LAGO/SWE-Duel | Medium (docker SWE-bench) | **runtime platform** |

## Selection: AFlow + mini-SWE-agent

**Why AFlow:** verified paper + public code + established MCTS workflow
search + cited by DAGO (2026) as the standard baseline → strongest
reproduction anchor and fairest comparison target.

**Why not GEPA primary:** prompt-level reflective mutation; less central to
*structural* agent evolution.

**Why not HarnessFix:** no verified source this session.

## Reproducibility status

- AFlow code URL verified; **commit/version NOT pinned yet** (needs clone +
  license check next stage).
- Real-model AFlow execution: `NOT_EXECUTED` (no API this round).
- Gate B = PASS for *feasibility*, not for completed reproduction.
