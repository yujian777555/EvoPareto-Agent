# Pilot 1 Behavioral Postmortem

**Source of truth:** `results/pilot1_live_run/pilot1_episode.json` (29-step raw trajectory)  
**Code under review:** `src/runtime/interactive_agent.py`, `behavioral_agent.py`, `episode_runner.py`, `src/agent/genome.py`  
**Real DeepSeek API calls this round: 0**  
**Recompute script:** `scripts/analyze_pilot1_postmortem.py` → `results/pilot1_postmortem/`

---

## 1. Action distribution (independently recomputed)

| Action | Count | Share |
|---|---:|---:|
| examine desk 1 | 16 | 55.2% |
| look | 7 | 24.1% |
| go to desk 1 | 3 | 10.3% |
| go to shelf 1 | 3 | 10.3% |
| **Total** | **29** | 100% |

Matches Planner observation exactly (`results/pilot1_postmortem/action_distribution.json`,
`matches_planner_observation: true`).

| Metric | Value | Definition |
|---|---:|---|
| Unique actions | 4 | \|set(actions)\| |
| Action repetition ratio | **0.862** | 1 − unique/total = 1 − 4/29 |
| Max consecutive same action | **4** | longest identical-action run |
| Max consecutive same observation | **4** | longest identical `observation_after` run |
| State–action loop **occurrences** | **21** | Σ (count−1) over repeated (state, action) pairs = EXTRA occurrences, not types |
| Repeated (state, action) pair **types** | **6** | distinct (state, action) pairs with count ≥ 2 |
| No-new-info action ratio | **0.276** (8/29) | steps where `observation_after == observation_before` |
| Obs-change-after-action ratio | **0.714** (20/28) | consecutive pairs where `observation_after[t] != observation_after[t-1]`; denominator T-1 = 28 |
| Unique locations visited | **2** (`desk 1`, `shelf 1`) | location tokens in obs / `go to` actions |
| Half-behavior divergence | **0.0** | 1 − Jaccard(action sets of halves) |
| Won | false | native `won` |
| Reflection count | 1 | genome reflection events |
| Per-step tokens/cost | NOT_OBSERVABLE_FROM_PILOT1 | trajectory has no per-step usage fields |

**First vs second half:** identical action *sets* (divergence 0.0). First half (14 steps)
vs second half (15 steps) only differ in counts — the agent did **not** change policy
after repeatedly failing.

## 2. Did the agent advance toward the goal?

Goal: `look at book under the desklamp.`

| Check | Evidence | Result |
|---|---|---|
| Actively search for a book? | no action text contains "book" | **No** |
| Enter region with target object? | `book_location_status = UNKNOWN_FROM_TRAJECTORY` | **Not observable** |
| Search for a desklamp? | no lamp/desklamp in any observation or action | **No** |
| Open container / take item / use light? | 0 open / 0 take / 0 use actions | **No** |
| Loop around desk 1 / shelf 1? | 26/29 steps at those two locations | **Yes** |
| Change action when observation unchanged? | see §3 | **Partly no** |
| Use newly available actions? | step-1 room listing offered drawer 1–3, bed 1, safe 1, garbagecan 1, sidetable 1–2, shelf 2–5 — never visited | **No** |
| Repeat legal but unprogressing commands? | 21 loop occurrences; 16× `examine desk 1` on an unchanging desk | **Yes** |

**Observed objects at desk 1:** cellphone 3, keychain 3, laptop 3, pen 2.  
**Observed objects at shelf 1:** cellphone 2, keychain 2.  
Book and desklamp **never appeared** in any of the 29-step observations.

**Book position is UNKNOWN_FROM_TRAJECTORY.** Failure to find it does not prove
where it is. Do not infer placement from this episode.

## 3. Loop structure (measurable)

Two oscillating observation templates dominate:

1. `On the desk 1, you see a cellphone 3, a keychain 3, a laptop 3, and a pen 2.` (from `examine desk 1`)
2. `You are facing the desk 1. Next to it, you see nothing.` (from `look`)

Steps 2–10: `examine×4 (identical obs) → look → examine → look → examine → examine(identical)`.  
Steps 11–29: `go shelf → go desk → look → examine` repeated three times, ending on `go to shelf 1`.

**Mathematical loop evidence:**
- 21 loop occurrences of (state, action) pairs
- 4 identical consecutive `examine desk 1` runs (twice: steps 2–5 and 21–22/27–28 pattern)
- 8/29 steps returned byte-identical observation to the input observation

## 4. Source-level failure mechanisms

### 4.1 Memory (`MemoryStore`)

```python
# behavioral_agent.py
def write(self, item):  # item = f"obs:{observation[:120]}"
    self.items.append(...)
def read(self, k=3):
    if self.strategy == "short_term":
        return self.items[-1:]      # ONLY THE LAST OBSERVATION
    return self.items[-k:]
```

- Writes **only** truncated observation text.
- **No** state / action / feedback / progress fields are recorded.
- `short_term` (Pilot 1 genome) keeps **one** line: the previous observation preview.
- Therefore the agent can never see "I already examined desk 1 five times".

**Mechanism for looping:** absence of action history and repetition counts in the
prompt makes every step look like a fresh decision problem.

### 4.2 Reflection (`self_critique`)

```python
# interactive_agent.py
if action is None and self.genome.reflection_strategy != "none":
    # retry prompt on PARSE FAILURE only
```

- Trigger condition: **parse failure** (`action is None`) only.
- A **legal but stagnant** action (e.g. 16th `examine desk 1`) never triggers reflection.
- All non-`none` strategies run the **same** retry prompt — no per-strategy logic.
- Name `self_critique` does **not** imply failure-driven self-critique.

Pilot 1: `reflection_count = 1` → exactly one parse failure occurred; 28 steps
"succeeded" as legal commands without any progress check.

### 4.3 Action parsing (`_parse_action`)

```python
first = t.splitlines()[0].strip()
for a in admissible:
    if first == a or t == a: return a, ""
tl = t.lower()
for a in admissible:
    if a.lower() in tl: return a, ""   # SUBSTRING MATCH
...
action = list(admissible)[0] if admissible else "look"  # FALLBACK = FIRST COMMAND
```

Risks (code-confirmed):
1. **Fuzzy substring match** — if the LLM emits "I should examine desk 1 carefully",
   any admissible command whose text appears as a substring wins (order-dependent).
2. **Fallback is deterministic** `admissible[0]` — in ALFWorld that is typically
   `go to bed 1` (alphabetically first in the step-1 listing). A persistent parse
   failure would send the agent to bed 1 every time.
3. No recording of `raw_response` / `parse_ok` / `used_fallback` into the Episode
   trajectory → **NOT_OBSERVABLE_FROM_PILOT1** whether the 16× `examine desk 1`
   were LLM choices or parser bias.

**Critical distinction:**  
LLM-chosen repetition vs parser-induced repetition **cannot be separated** from
Pilot 1 data. Must be marked `NOT_OBSERVABLE_FROM_PILOT1`.

### 4.4 Reasoning budget

```python
# BudgetMeter.from_reasoning_budget(64, horizon=30)
max_steps = round(30 * (0.5 + 64/128)) = 30
max_tokens = max(64, 64*12) = 768
# every LLM call: budget.charge(steps=1, tokens≈len(text)/4)
# reflection retry: another charge(steps=1)
```

| Semantic | Value |
|---|---:|
| Environment actions | 29 |
| LLM calls | 30 |
| Budget steps charged | 30 (29 selects + 1 reflection retry) |
| max_steps | 30 |
| termination | `budget_exhausted` |

The episode ended because **budget steps hit max_steps=30**, not because the
environment finished. One reflection call consumed one of the 30 step charges —
reflection competes with acting for the same budget pool.

## 5. Causal hypothesis table

| Hypothesis | Supporting evidence | Counter-evidence / uncertainty | How to verify |
|---|---|---|---|
| H1: Missing action history causes looping | Memory stores only last obs; 21 loop occurrences; no "already did this" signal | Cannot prove the LLM would stop looping even with history | A/B: same genome ± action-history in prompt; measure loop rate (offline + live) |
| H2: Reflection does not handle stagnation | Reflection only on parse failure; 0 stagnation triggers in 29 steps | Only 1 parse failure observed — low power | Instrument reflection triggers; add stagnation counter and see if it fires |
| H3: Parser/fallback induces repeats | Substring match + first-command fallback in code | No raw_response/parse_ok in Pilot 1 → **NOT_OBSERVABLE** | Log raw_response & parse_ok next run; count fallbacks |
| H4: Planner ignores task progress | No book/lamp-directed action despite goal text | Prompt does include the goal every step; model may simply fail the task | Compare with explicit "subgoals" prompt variant |
| H5: Genome phenotypes insufficiently distinct | tool_policy unused; planner=cot prompt-only; reflection strategies identical | memory & budget do change execution | See GENOME_PHENOTYPE_AUDIT.md |

**Constraint:** a single failed trajectory supports *diagnostic hypotheses*, not
unique causal proof. No hypothesis above is confirmed as the sole cause.

## 6. Missing data (explicit)

```
NOT_OBSERVABLE_FROM_PILOT1:
  raw_llm_response, parse_ok, parse_failure_reason, used_fallback,
  per_step_tokens, per_step_cost, reflection_trigger_step,
  book_desklamp_ground_truth_location
```

Pilot 1 trajectory schema only stores: step, observation_before/after,
admissible_commands, action, score, won, done, llm_call_count.
