"""Fault injection channels (ground truth → execution behavior).

Policy never sees these. Interpreter sees them as behavioral channels.
"""
from __future__ import annotations

from typing import Dict

from src.research.fceol_r1.task_suite import (
    FAULT_COMPOUND,
    FAULT_CONTEXT_PROPAGATION_ERROR,
    FAULT_RECOVERY_BRANCH_ERROR,
    FAULT_TOOL_ROUTING_ERROR,
    FAULT_VERIFICATION_OMISSION,
    TaskInstance,
)

# fault -> channels
_CHANNELS = {
    FAULT_VERIFICATION_OMISSION: {"verifier_sabotaged": True},
    FAULT_RECOVERY_BRANCH_ERROR: {"recovery_miswired": True},
    FAULT_TOOL_ROUTING_ERROR: {"tool_is_broken": True},
    FAULT_CONTEXT_PROPAGATION_ERROR: {"context_dropped": True},
    FAULT_COMPOUND: {"tool_is_broken": True, "recovery_miswired": True},
}


def fault_channels(task: TaskInstance) -> Dict[str, bool]:
    base = {
        "tool_is_broken": False,
        "verifier_sabotaged": False,
        "context_dropped": False,
        "recovery_miswired": False,
    }
    base.update(_CHANNELS.get(task.fault_type, {}))
    return base
