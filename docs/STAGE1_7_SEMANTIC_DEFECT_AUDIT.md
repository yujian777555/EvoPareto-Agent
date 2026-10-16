# Stage 1.7 Semantic Defect Audit

**Real API: 0.** Fixes for Stage 1.6-confirmed defects.

| Defect | Symptom | Fix | Evidence |
|---|---|---|---|
| **A1 put-goal parse** | `target_object_name=""` for `put a alarmclock in dresser` | `src/runtime/goal_grounding.py::parse_goal` → `GoalSpec(task_family, target_object, target_receptacle, required_relation)` | `test_parse_put_alarmclock_in_dresser` |
| **A2 task type** | `_task_type` never set on live path | derived from public goal text in `select_action` (`parse_goal(...).task_family`) | `test_task_type_derived_from_goal` |
| **A3 light_on in held** | `held_objects=["light_on"]` | inventory vs `world_facts` split; `light_on` excluded from held | `test_light_on_not_in_held` |
| **A4 memory none** | `k=0 → None → all history` | `history_lines(k=0)=[]`; explicit none→0, short_term→1, else 3 | `test_memory_none_gets_zero_history` |

Goal text is used for **names only** (object/receptacle/tool); discovery truth
still comes from environment feedback (Stage 1.6 evidence rules kept).
