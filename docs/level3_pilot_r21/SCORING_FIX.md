# Scoring Fix & Parent Re-verification (Tasks B/C/E)

## What was wrong

| Version | Parent | Child | Why |
|---|---:|---:|---|
| original top-level | 0/12 | 11/12 | extractor picked the tuple `cost` (0.0) as the answer |
| first RESCORED | 2/12 | 11/12 | repr-parsing of 200-char-truncated text |
| **this re-verification** | **10/12** | **11/12** | full raw output + tuple unpacked at the data layer |

The original "child improved 9" was an **artifact of broken parent scoring**.

## Fixed normalisation

Parent workflow returns `(response_text, cost)`. The normalisation layer now
unpacks the tuple at the data layer — never by parsing truncated repr strings.
Full raw responses are saved. Answers are extracted with `####` / `Answer:` /
terminal `= N` heuristics.

## Corrected paired result (12 held-out GSM8K test tasks)

| | Parent | Child |
|---|---:|---:|
| correct | **10** / 12 | **11** / 12 |
| accuracy | 0.833 | 0.917 |

Paired: improved **1**,
regressed **0**,
both correct **10**,
both wrong **1**,
net gain **+1**.

**The child is only marginally better (+1 task). This is within noise for n=12.**
The previous +9 conclusion does NOT survive rescoring.

## Parent source vs execution SHA (Task C)

| Field | SHA |
|---|---|
| source_graph_sha256 (bytes) | `ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e` |
| execution_graph_sha256 (bytes) | `ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e` |
| byte_identical | **True** |
| execution_graph_sha256 (text-normalised) | `a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe` |
| scoring_adapter_sha256 | `05bed57ccd6158ab…` |

Source and frozen graph are **byte-identical**. The `a92febff…` figure in the
per-task records is the SHA of the LF-normalised text (Python `read_text()`
universal newlines) — same content, different newline representation.

## Caveat (honest)

The child also uses **multi-sample self-consistency voting** and an **explicit
answer format**. This is a **system-level workflow comparison**, not an isolated
attribution to the evolutionary algorithm.
