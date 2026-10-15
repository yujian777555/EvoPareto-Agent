"""Native ALFWorld TextWorld smoke: real init_env / reset / step."""

import os
import json

os.environ.setdefault("ALFWORLD_DATA", "/root/.cache/alfworld")
DATA = os.environ["ALFWORLD_DATA"]

from alfworld.agents.environment.alfred_tw_env import AlfredTWEnv

# Check data layout
for sub in ("json_2.1.1", "json_2.1.1/json", "json_2.1.1/pddl", "json_2.1.1/tw-pddl"):
    p = os.path.join(DATA, sub)
    print("exists", p, os.path.isdir(p))

config = {
    "general": {"training_method": "dagger"},
    "env": {
        "goal_desc_human_anns_prob": 0.0,
        "task_types": [0, 1, 2, 3, 4, 5, 6],
        "domain_randomization": False,
        "expert_type": "planner",
    },
    "dataset": {
        "data_path": os.path.join(DATA, "json_2.1.1", "valid_train"),
        "eval_id_data_path": os.path.join(DATA, "json_2.1.1", "valid_seen"),
        "eval_ood_data_path": os.path.join(DATA, "json_2.1.1", "valid_unseen"),
        "num_train_games": 3,
        "num_eval_games": 2,
    },
    "dagger": {"training": {"max_nb_steps_per_episode": 50}},
    "rl": {"training": {"max_nb_steps_per_episode": 50}},
}

print("train path exists", os.path.isdir(os.path.expandvars(config["dataset"]["data_path"])))
env_wrap = AlfredTWEnv(config=config, train_eval="eval_out_of_distribution")
print("num_games", env_wrap.num_games)
assert env_wrap.num_games > 0, "no games found"

gym_env = env_wrap.init_env(batch_size=1)
print("gym_env", type(gym_env).__name__)

# Official batch API: reset returns obs batch + infos
reset_out = gym_env.reset()
print("reset_type", type(reset_out), "len", len(reset_out) if isinstance(reset_out, tuple) else "n/a")
obs = reset_out[0] if isinstance(reset_out, tuple) else reset_out
infos = reset_out[1] if isinstance(reset_out, tuple) and len(reset_out) > 1 else {}
print("obs0", str(obs[0])[:250] if isinstance(obs, (list, tuple)) else str(obs)[:250])
print("infos_keys", list(infos.keys())[:20] if isinstance(infos, dict) else type(infos))

adm = infos.get("admissible_commands") if isinstance(infos, dict) else None
print("adm", str(adm)[:300])

action = "look"
if isinstance(adm, list) and adm:
    a0 = adm[0]
    if isinstance(a0, (list, tuple)) and a0:
        action = a0[0]
    elif isinstance(a0, str):
        action = a0
print("action", action)

step_out = gym_env.step([action])
print("step_len", len(step_out))
for i, part in enumerate(step_out):
    print(f"part{i}", type(part).__name__, str(part)[:180])

print("SMOKE_OK")
