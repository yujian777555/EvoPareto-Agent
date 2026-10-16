# Controlled Fault Protocol

Channels (ground truth → execution only):

| Fault | Channels | Fixable by operators? |
|---|---|---|
| VERIFICATION_OMISSION | verifier_sabotaged | **No** (no op disables verifier) |
| RECOVERY_BRANCH_ERROR | recovery_miswired | **No** (recovery always hurts) |
| TOOL_ROUTING_ERROR | tool_is_broken | **Yes** (M1+M2 → route/repair) |
| CONTEXT_PROPAGATION_ERROR | context_dropped | **Yes** (M1+M2 restore constraint) |
| COMPOUND_RECOVERY_ROUTING | both | **No** |

Symptom ambiguity preserved: `wrong_output_submitted` maps to
{VERIFICATION, PLANNING}. Same operator can help or hurt (complexity cost).
Not a lookup table — optimal sequence is non-obvious (oracle uses search).
