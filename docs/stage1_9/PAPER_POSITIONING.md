# Paper Positioning

## Candidates

### 1. Experience-guided Pareto Evolution for LLM Agent Configuration
- **Q:** Does Pareto-credit operator memory speed multi-objective agent search?
- **Delta vs closest (MOAE/RSI-Router/AOS):** operator-utility transfer + equal-budget comparison vs bandit AOS.
- **Evidence needed:** H1 on EvalPlus; distribution-shift proof; 8-arm tables.
- **Risk:** reviewers say "AOS redux"; engineering-heavy, insight-light.
- **Exit if:** H1 falsified vs UCB-AOS.

### 2. Preference-adaptive Multi-objective Evolution of LLM Agents
- **Q:** Does **dynamic** preference tracking improve region-of-interest search?
- **Delta:** true closed-loop preference (vs fixed presets in current PPEC).
- **Evidence needed:** H2; ablate fixed vs dynamic; global-HV safety bound.
- **Risk:** CRAFT already argues trade-off should be post-hoc — must beat that.
- **Exit if:** dynamic ≈ fixed weights.

### 3. Joint Memory- and Preference-driven Evolutionary Agent Search
- **Q:** Is there a super-additive PEEM×PPEC interaction under hard API budgets?
- **Delta:** factorial design + anytime HV + physical budget accounting.
- **Evidence needed:** H3 2×2 interaction; full 8-arm; held-out tasks.
- **Risk:** doubles novelty burden; interaction may be zero.
- **Exit if:** interaction CI includes 0.

## Recommended primary

**#2 Preference-adaptive multi-objective agent-configuration search**, with
PEEM as a supporting efficiency mechanism (not the headline). Rationale: the
2026 landscape already saturates "Pareto agent evolution" stories; *dynamic
preference under expensive evaluations* is narrower, falsifiable, and matches
the one piece of infrastructure we truly have (strict budget gate).

## CCF B feasibility

**Conditional / not guaranteed.** Missing today: any non-zero agent success on
a respectable benchmark; phenotype-validated genome; dynamic PPEC
implementation; ≥8-arm comparison; held-out generalization. If Plan A fails to
show performance spread, target a workshop / findings track or pivot to
budget-allocation methodology papers.
