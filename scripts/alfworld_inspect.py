import os

import alfworld

root = os.path.dirname(alfworld.__file__)
print("root", root)
for dirpath, dirnames, filenames in os.walk(root):
    for fn in filenames:
        if fn.endswith((".yaml", ".yml", ".json", ".toml")) or "config" in fn.lower():
            print(os.path.join(dirpath, fn))
# print collect_game_files source snippet
import inspect

from alfworld.agents.environment.alfred_tw_env import AlfredTWEnv

print("--- collect_game_files ---")
print(inspect.getsource(AlfredTWEnv.collect_game_files)[:2000])
print("--- reset ---")
print(inspect.getsource(AlfredTWEnv.reset)[:1500])
print("--- step ---")
print(inspect.getsource(AlfredTWEnv.step)[:1500])
