"""Native ALFWorld TextWorld adapter (Phase5-R3-R2 Stage C).

Requires: alfworld + game data (Docker volume `alfworld-data` or local install).

Success comes ONLY from environment `won` / score — never capability prior.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.benchmark.split_integrity import (
    SplitIntegrityError,
    normalize_game_id,
    resolve_split,
    validate_game_in_split,
)
from src.runtime.result import EpisodeResult, TaskResult


class NativeALFWorldUnavailable(RuntimeError):
    pass


def alfworld_available() -> bool:
    try:
        import alfworld  # noqa: F401

        data = os.environ.get("ALFWORLD_DATA", "")
        return bool(data) or os.path.isdir(os.path.expanduser("~/.cache/alfworld"))
    except Exception:
        return False


@dataclass
class NativeALFWorldConfig:
    data_path: str = ""
    split: str = "valid_unseen"  # held-out by default
    num_games: int = 2
    max_steps: int = 30
    batch_size: int = 1
    seed: int = 0


class NativeALFWorldEnv:
    """Thin wrapper over official AlfredTWEnv + TextWorld gym batch API."""

    def __init__(self, config: Optional[NativeALFWorldConfig] = None) -> None:
        self.config = config or NativeALFWorldConfig()
        if not alfworld_available():
            raise NativeALFWorldUnavailable(
                "alfworld package/game data missing; see docs/PHASE5_R3_R2_NATIVE_SETUP.md"
            )
        self._env = None
        self._games: List[str] = []
        self.last_reset_meta: Dict[str, Any] = {}

    def _cfg_dict(self) -> Dict[str, Any]:
        from src.benchmark.split_integrity import data_dir_for, resolve_split

        data = self.config.data_path or os.environ.get(
            "ALFWORLD_DATA", os.path.expanduser("~/.cache/alfworld")
        )
        train_eval, _rel = resolve_split(self.config.split)
        split_path = data_dir_for(self.config.split, data)
        return {
            "general": {"training_method": "dagger"},
            "env": {
                "goal_desc_human_anns_prob": 0.0,
                "task_types": [0, 1, 2, 3, 4, 5, 6],
                "domain_randomization": False,
                "expert_type": "planner",
            },
            "dataset": {
                "data_path": split_path,
                "eval_id_data_path": data_dir_for("valid_seen", data),
                "eval_ood_data_path": data_dir_for("valid_unseen", data),
                "num_train_games": self.config.num_games,
                "num_eval_games": self.config.num_games,
            },
            "dagger": {"training": {"max_nb_steps_per_episode": self.config.max_steps}},
            "rl": {"training": {"max_nb_steps_per_episode": self.config.max_steps}},
        }

    def reset(self, *, episode_index: int = 0, force_game_file: Optional[str] = None):
        from alfworld.agents.environment.alfred_tw_env import AlfredTWEnv

        from src.benchmark.split_integrity import (
            normalize_game_id,
            resolve_split,
            validate_game_in_split,
        )

        train_eval, _ = resolve_split(self.config.split)  # fail-closed
        wrap = AlfredTWEnv(config=self._cfg_dict(), train_eval=train_eval)
        if wrap.num_games == 0:
            raise NativeALFWorldUnavailable(f"no games for split={self.config.split}")
        self._games = [normalize_game_id(g) for g in wrap.game_files]
        idx = 0
        if force_game_file:
            target = normalize_game_id(force_game_file)
            matches = [i for i, g in enumerate(self._games) if g == target]
            if not matches:
                raise SplitIntegrityError(f"forced game not in split games: {target}")
            if len(matches) > 1:
                raise SplitIntegrityError(f"ambiguous forced game id: {target}")
            idx = matches[0]
            chosen = self._games[idx]
        elif self._games:
            idx = int(episode_index) % len(self._games)
            chosen = self._games[idx]
        else:
            chosen = ""
        wrap.game_files = [chosen] if chosen else wrap.game_files
        wrap.num_games = 1 if chosen else wrap.num_games
        self._env = wrap.init_env(batch_size=self.config.batch_size)
        obs, infos = self._env.reset()
        # Split integrity: actual game must belong to requested split.
        actual = ""
        if isinstance(infos, dict):
            gf = infos.get("extra.gamefile") or infos.get("gamefile")
            if gf:
                actual = normalize_game_id(str(gf[0] if isinstance(gf, (list, tuple)) else gf))
        if not actual and chosen:
            actual = chosen
        validate_game_in_split(actual, self.config.split)
        if isinstance(infos, dict):
            infos = dict(infos)
            infos["extra.gamefile"] = [actual]
            infos["requested_split"] = self.config.split
            infos["resolved_train_eval"] = train_eval
            infos["actual_game_id"] = actual
        self.last_reset_meta = {
            "requested_split": self.config.split,
            "resolved_train_eval": train_eval,
            "dataset_path": self._cfg_dict()["dataset"]["data_path"],
            "actual_game_id": actual,
        }
        return obs, infos

    def step(self, actions: Sequence[str]):
        return self._env.step(list(actions))

    def close(self) -> None:
        try:
            if self._env is not None:
                self._env.close()
        except Exception:
            pass


@dataclass
class NativeALFWorldAdapter:
    """BenchmarkAdapter-compatible native evaluator."""

    name = "alfworld_textworld"
    config: NativeALFWorldConfig = field(default_factory=NativeALFWorldConfig)
    evaluation_kind = "real_environment"

    def __init__(self, config: Optional[NativeALFWorldConfig] = None) -> None:
        self.config = config or NativeALFWorldConfig()
        self.name = "alfworld_textworld"
        self.evaluation_kind = "real_environment"
        self._env: Optional[NativeALFWorldEnv] = None
        self._last_episodes: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self._env = NativeALFWorldEnv(self.config)
        self._env.reset()

    def run_episode_with_policy(
        self,
        policy,
        *,
        max_steps: Optional[int] = None,
        seed: int = 0,
    ) -> Dict[str, Any]:
        """policy(observation, admissible_commands) -> action string."""
        if self._env is None:
            self.reset()
        assert self._env is not None
        obs, infos = self._env.reset()
        # batch size 1
        o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
        adm = []
        if isinstance(infos, dict):
            a = infos.get("admissible_commands")
            if a:
                adm = list(a[0]) if isinstance(a[0], (list, tuple)) else list(a)
        max_s = max_steps or self.config.max_steps
        trajectory: List[Dict[str, Any]] = []
        success = False
        steps = 0
        score = 0
        for t in range(max_s):
            action = policy(o0, adm)
            out = self._env.step([action])
            # batch API: (obs, scores, dones, infos)
            obs, scores, dones, infos = out[0], out[1], out[2], out[3]
            o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
            score = scores[0] if isinstance(scores, (list, tuple)) else scores
            done = dones[0] if isinstance(dones, (list, tuple)) else dones
            won = False
            if isinstance(infos, dict):
                w = infos.get("won")
                if w is not None:
                    won = bool(w[0] if isinstance(w, (list, tuple)) else w)
                a = infos.get("admissible_commands")
                if a:
                    adm = list(a[0]) if isinstance(a[0], (list, tuple)) else list(a)
            trajectory.append({
                "t": t, "action": action,
                "obs": str(o0)[:200], "score": float(score),
                "won": won, "done": bool(done),
            })
            steps = t + 1
            if won or done:
                success = won
                break
        return {
            "benchmark": self.name,
            "evaluation_kind": "real_environment",
            "success": bool(success),
            "steps": steps,
            "score": float(score),
            "trajectory": trajectory,
        }

    def evaluate_policy(self, policy, *, n_episodes: int = 2) -> EpisodeResult:
        ep = EpisodeResult(agent_id=0)
        self.reset()
        for i in range(n_episodes):
            out = self.run_episode_with_policy(policy, seed=i)
            ep.append(TaskResult(
                task_id=f"native-{self.config.split}-{i}",
                success=out["success"],
                steps=out["steps"],
                tokens=0,
                latency=0.0,
                cost=0.0,
                metadata={
                    "evaluation_kind": "real_environment",
                    "score": out["score"],
                    "trajectory": out["trajectory"],
                    "split": self.config.split,
                },
            ))
            self._last_episodes.append(out)
        return ep


def random_policy(obs, admissible):
    import random

    if admissible:
        return random.choice(admissible)
    return "look"
