"""RL training (PKG-9). DDPG primary + PPO backup, sb3-based.

See .agent/plans/pkg-9-ddpg-ppo-backup.md.
"""

from src.rl_training.core import RewardScaleWrapper, train_rl
from src.rl_training.ddpg_trainer import load_ddpg_config, train_ddpg
from src.rl_training.ppo_trainer import load_ppo_config, train_ppo

__all__ = [
    "RewardScaleWrapper",
    "train_rl",
    "train_ddpg",
    "train_ppo",
    "load_ddpg_config",
    "load_ppo_config",
]
