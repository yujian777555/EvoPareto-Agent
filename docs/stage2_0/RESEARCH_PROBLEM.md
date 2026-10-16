# Research Problem (Stage 2.0)

**Question:** Can an evolutionary algorithm learn which structural mutations
are effective under different LLM-agent failure mechanisms, using verified
intervention outcomes rather than only aggregate fitness?

**Method (working name):** Failure-Conditioned Evolutionary Operator Learning
(FCEOL).

## Why this is not the old story

Old framing (PEEM/PPEC multi-objective agent search) collided with 2026 work
(MOAE, Harmony Harness, RSI-Router) and PEEM ≈ classic AOS. New framing:

- Failure **evidence** is a conditioning state (not just a scalar fitness).
- Mutation **structure** is an executable workflow genome (not prompt labels).
- Credit comes from **paired intervention outcomes** Δ=R(child)−R(parent),
  not from an LLM's explanation.
- Transfer is measured on **held-out fault instances**.

## Not claimed

- Not "agent that diagnoses and fixes itself".
- Not a new bandit algorithm (FCEOL is contextual-bandit-style UCB over
  failure contexts — honestly labeled).
- Not causal proof from single Δ (paired contrast estimate only).
