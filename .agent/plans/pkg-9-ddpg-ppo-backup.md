# Feature: PKG-9 — DDPG trainer + PPO backup

> The RL track. Replicate **DDPG** (Xiong et al, paper gốc) on Vietnam VN30
> with PPO as a backup to handle divergence. Two trainers, same interface,
> shared eval loop. Output: trained model `.zip` files + per-checkpoint
> validation metrics, ready to be wrapped by an Agent Protocol class
> for PKG-10 backtest.
>
> Critical risk: DDPG is known to diverge on small custom envs (PRD §14
> Risk #7). PPO backup train song song means if DDPG Q-value blows up,
> we still have an RL baseline for the report.

## Feature Description

Two trainer modules (`ddpg_trainer.py`, `ppo_trainer.py`) + a shared `RLAgent`
wrapper that implements the `Agent` Protocol (`src/agent_base.py`). After
training:

1. CLI `scripts/train_ddpg.py` runs DDPG on `train` split (~1500 sessions,
   6 years), with periodic eval on `val` split (~82 sessions, Q1 2025).
   Best model on val saved to `results/models/ddpg_best.zip`.
2. CLI `scripts/train_ppo.py` does the same with PPO. Outputs
   `results/models/ppo_best.zip`.
3. `RLAgent(model_path)` loads either, exposes `decide(obs, info) → action`
   so PKG-10 can plug it into `run_backtest` exactly like baselines + LLM
   agents.
4. Divergence detection: trainer monitors actor/critic loss + Q-value
   magnitude; if any NaN/Inf or |Q| > threshold for N consecutive steps,
   abort + log + emit machine-readable status (CLI exit code 2). PPO
   trainer fires automatically as the backup path if DDPG aborts.

Acceptance criteria (Issue #10):
- DDPG train completes; val Sharpe ≥ -0.5 (sanity, not "good")
- Q-value blow up → automatic fallback PPO + log warning
- Models saved at `results/models/{ddpg,ppo}_best.zip`

Decision frequency: **daily** (PRD §15 — DDPG daily, LLM weekly). The env
already steps daily; agent emits action each step. No weekly cache (unlike
LLM agents).

## User Story

As a **PKG-10 backtest runner**
I want to **construct `RLAgent("results/models/ddpg_best.zip")` and pass
it to `run_backtest`** without knowing sb3 internals
So that **DDPG / PPO compete on the same evaluation harness as baselines
and LLM agents — same env, same seed, same metrics**.

As a **report writer (Person 1)**
I want **val Sharpe + per-checkpoint loss curves saved to JSONL**
So that **the report's "training stability" section has concrete numbers,
and the appendix can show learning curves**.

As a **Person 2 (verifier)**
I want **divergence detection that fires loudly, not silently**
So that **a hidden NaN in critic loss doesn't masquerade as a "trained"
model that secretly emits garbage**.

As a **deadline-bound solo dev (Duc)**
I want **PPO backup as a parallel track triggered by DDPG failure**
So that **the RL leg of the comparison still ships even in the worst
case where DDPG never converges by 31/05**.

## Problem Statement

5 distinct challenges:

1. **DDPG stability on small custom envs.** Xiong et al used Dow30 + 5+
   years; we have VN30 / 5 tickers / 6 years. Replay buffer fills slowly,
   target network update can amplify noise. PRD §14 Risk #7 explicitly
   names "DDPG diverge / Q-value explode" as a top-3 risk.
2. **Action space semantics.** Env action is `Box(-1, 1, (5,))` but env
   clips negatives to 0 (long-only). DDPG actor outputs in `[-1, 1]` after
   tanh — the negative half is wasted exploration. We need action noise
   tuned so the agent doesn't oscillate in the dead zone forever.
3. **Reward scale.** Env reward is `log(pv_t / pv_{t-1})` — typically
   `[-0.01, +0.01]` per step. DDPG critic loss can struggle with such
   small targets. Need reward scaling OR target network learning rate
   tuned for this scale.
4. **Train wall-time.** 1500 sessions × N episodes × neural network
   forward/backward on CPU (torch 2.12 CPU detected) = potentially hours.
   Need a sane `total_timesteps` budget (~50K-100K for DDPG, ~200K for
   PPO) that fits in a few hours on dev machine.
5. **Reproducibility.** PRD §15 §5 "same seed → same trajectory". sb3
   handles seeds but env + numpy + torch all need seeding. Verify with
   2-run determinism test in the smoke.

## Solution Statement

10 design decisions LOCK before code:

- **D1.** Shared `train_rl` core in `src/rl_training/` — DDPG + PPO are
  thin wrappers passing algo-specific hyperparams + sb3 class
- **D2.** Hyperparams live in `configs/{ddpg,ppo}.yaml`, loaded via PyYAML
  at train time. Single source of truth, easy to A/B
- **D3.** Action noise = `NormalActionNoise(mean=0, sigma=0.1)` for DDPG;
  sigma decays linearly to 0.02 over training (sb3 doesn't auto-decay;
  callback handles it)
- **D4.** Validation = roll out trained policy on `val` split env every
  N steps; track cumulative return + Sharpe; save best model when Sharpe
  improves OR cum_return improves. Sb3's `EvalCallback` provides this
- **D5.** Divergence guard = custom `DivergenceCallback`: NaN in loss → abort;
  |Q-value| > 1e6 sustained 100 steps → abort. Sets `model._aborted_reason`
  for CLI exit code
- **D6.** `RLAgent` wrapper implements Agent Protocol; `decide()` calls
  `model.predict(obs, deterministic=True)` then returns action
- **D7.** PPO is the "always works" backup — no action noise, no Q-value
  to blow up. Same total_timesteps budget. If DDPG aborts, PPO is the
  RL representative in the report
- **D8.** Reward scaling = 100× the env reward (log-return × 100 ≈ unit
  scale). Optional via `--reward-scale` flag; default 100 for DDPG,
  default 1 for PPO (clip-ratio handles scale)
- **D9.** Checkpointing every 10K steps + best model on val improvement.
  Final model = best-on-val (NOT last-trained, which often overfits)
- **D10.** Training log = JSONL per-eval-interval: `{step, val_cum_return,
  val_sharpe, mean_episode_reward, actor_loss, critic_loss, q_value_mean}`.
  PKG-10 + Person 1 read this for learning curves

## Feature Metadata

- **Feature Type:** New Capability (the RL pillar of the comparison)
- **Estimated Complexity:** **Medium-High** — sb3 itself is well-trodden
  but DDPG-on-custom-env is failure-prone; divergence detection +
  reward scaling need careful tuning
- **Primary Systems Affected:**
  - New module dir: `src/rl_training/` (replaces flat
    `src/ddpg_trainer.py` per PRD scaffolding — better tested
    pattern from PKG-8 multi_agent/)
  - New `configs/` dir at repo root
  - 2 new CLI scripts
  - `src/agents/` module for `RLAgent` wrapper (NOT
    `src/agents/__init__.py` registry — that's PKG-S serialized)
  - `tests/test_rl_*.py`
  - `results/models/` (gitignored)
- **Dependencies:**
  - `stable-baselines3>=2.3` ✅ installed (2.8.0)
  - `torch` ✅ (2.12.0+cu130 CPU, no GPU on dev WSL2)
  - `PyYAML` — NEEDS to be added to `pyproject.toml` (not currently a dep)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — ĐỌC TRƯỚC KHI IMPLEMENT

**Env contract (PKG-3, MUST match):**

- `src/trading_env.py` (entire file ~239 lines) — `VNTradingEnv` is the env.
  Critical invariants:
  - `action_space = Box(-1, 1, (5,), float32)` — DDPG/PPO output fits exactly
  - `observation_space = Box(-inf, inf, (56,), float32)` — model input
  - `reward = log(pv_t / pv_{t-1})` typical range `[-0.01, +0.01]`
  - `_clean_action` clips negatives to 0 + renormalizes if sum > 1
  - Terminates on end-of-data OR `pv ≤ 0` (catastrophic loss reward = -100)
  - Already calls `np.nan_to_num` on obs — won't crash sb3 mid-train
- `src/env_data_loader.py:43-100` — `load_market_data("train")` →
  ~1500 sessions, ~6 years. `MarketData.dates` is the env clock.

**Agent Protocol + Backtest (PKG-3/4):**

- `src/agent_base.py` (~56 lines) — `Agent` Protocol + `BacktestResult` dataclass
- `src/baselines.py:97-124` — `run_backtest(env, agent, seed)` — what `RLAgent`
  must work with end-to-end
- `src/baselines.py:_snapshot, _records_to_frames` — internal helpers for CLI

**Config (PKG-0):**

- `src/config.py` — `TICKERS`, `INITIAL_CAPITAL`, `TRAIN_START`, `VAL_START`,
  `TEST_START`, `TEST_END`, `LOT_SIZE`, `BUY_FEE`, `SELL_FEE`, `PRICE_BAND`,
  `PROJECT_ROOT`. **No new constants needed** — RL hyperparams live in
  `configs/*.yaml`.

**Pattern bắt buộc mirror:**

- `src/llm/multi_agent/agent.py` (PKG-8, entire file ~265 lines) — class shape
  + Agent Protocol fulfillment + audit log pattern. RLAgent is simpler
  (no graph, no transcript, no timeout) but follows the same conventions.
- `scripts/run_single_agentic.py` (PKG-7, ~190 lines) — CLI pattern for
  backtest runners. PKG-9 has TRAIN scripts (separate) + a wrapper backtest
  for sanity, but the shape is the same.
- `tests/test_baselines.py` — `RandomAgent` test pattern; demonstrates how
  agent + env + run_backtest test together with synthetic_market_data.
- `tests/conftest.py:synthetic_market_data` — 60-session fixture; PKG-9
  tests will train DDPG on this for 1000-step smoke (NOT for performance
  validation — just non-NaN + save/load round-trip).

**Read-only context (don't modify):**

- `CLAUDE.md` §"Domain-Specific Rules" §1 (no lookahead), §3 (VN rules
  in env, not callsite — DDPG operates at decision layer, env handles
  execution), §5 (reproducibility — seed everything).
- `CLAUDE.md` §"Error handling" — "DDPG diverge / NaN Q-value → log
  warning, fall back to PPO. Don't silently train forever."
- `CLAUDE.md` §"Patterns" → "Decision layer ≠ execution layer" — RL agent
  emits weights in `[-1, 1]`, env clamps + lots + fees.
- `.agent/PRD.md` §7 Feature 3 (DDPG description), §15 (locked params),
  §14 Risk #7 (DDPG diverge mitigation).
- GitHub Issue #10 (PKG-9 spec).
- Xiong et al paper (in `docs/`): "Deep Reinforcement Learning Approach
  for Stock Trading" — Section 4 hyperparams + Section 5 results.

**Don't touch (file ownership):**

- `src/trading_env.py`, `src/env_data_loader.py`, `src/baselines.py`,
  `src/agent_base.py` — PKG-3/4 (merged).
- `src/llm/*` — PKG-5/6/7/8 (merged).
- `src/agents/__init__.py` — PKG-S serialized (don't create yet, but you
  CAN put `RLAgent` in `src/agents/rl_agent.py` — sibling file).
- `src/eval/*` — PKG-10 (next package).

### New Files to Create

```
src/rl_training/
├── __init__.py
├── core.py                       # shared train_rl() + callbacks
├── ddpg_trainer.py               # train_ddpg(env_factory, cfg, save_path)
├── ppo_trainer.py                # train_ppo(env_factory, cfg, save_path)
└── callbacks.py                  # DivergenceCallback, ValMetricsCallback,
                                  # ActionNoiseDecayCallback

src/agents/
└── rl_agent.py                   # RLAgent class — wraps sb3 model

configs/
├── ddpg.yaml                     # DDPG hyperparams
└── ppo.yaml                      # PPO hyperparams

scripts/
├── train_ddpg.py                 # CLI: train DDPG
├── train_ppo.py                  # CLI: train PPO
└── run_rl_backtest.py            # CLI: load RLAgent, run backtest on test

tests/
├── test_rl_callbacks.py          # DivergenceCallback, ValMetricsCallback
├── test_rl_agent.py              # RLAgent Protocol, save/load round-trip
└── test_ddpg_smoke.py            # train 1000 steps on synthetic → no NaN

results/
├── models/{ddpg,ppo}_best.zip    # gitignored
├── ddpg_training_log.jsonl       # per-eval metrics
└── ppo_training_log.jsonl
```

### Relevant Documentation — ĐỌC TRƯỚC KHI IMPLEMENT

- **stable-baselines3 DDPG:**
  https://stable-baselines3.readthedocs.io/en/master/modules/ddpg.html
  - Constructor: `DDPG(policy, env, learning_rate, buffer_size,
    learning_starts, batch_size, tau, gamma, action_noise, train_freq,
    gradient_steps, policy_kwargs, verbose, seed)`
  - Key gotcha: `learning_starts` must be > 0 (default 100) — otherwise
    NaN on empty replay buffer
- **stable-baselines3 PPO:**
  https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html
  - On-policy; no replay buffer; `n_steps` × `n_envs` per update
  - Far more stable than DDPG on small custom envs — our backup
- **sb3 callbacks:**
  https://stable-baselines3.readthedocs.io/en/master/guide/callbacks.html
  - `BaseCallback._on_step()` returns `False` to abort training cleanly
  - `BaseCallback.logger` has access to training metrics
  - `EvalCallback(eval_env, best_model_save_path, n_eval_episodes,
    eval_freq, deterministic)` — built-in best-on-val saving
- **gymnasium env compatibility:**
  https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html
  - sb3 2.x supports gymnasium directly; our env passes `check_env` (verify
    in Spike A)
- **NormalActionNoise:**
  https://stable-baselines3.readthedocs.io/en/master/modules/ddpg.html#parameters
  - `NormalActionNoise(mean=np.zeros(n), sigma=σ*np.ones(n))`
  - σ=0.1 is sb3 default; we decay to 0.02 over training
- **Xiong et al paper** (in `docs/`):
  - Section 4.2 hyperparams: γ=0.99, τ=0.005, learning_rate=1e-4,
    buffer=1M, batch=128. We'll start from these.
- **PyYAML:**
  https://pyyaml.org/wiki/PyYAMLDocumentation
  - `yaml.safe_load(open(path))` — safe load (no Python objects)

### Pre-implementation spikes

**Spike A — sb3 env compatibility check:**

```bash
.venv/bin/python <<'PY'
"""Verify VNTradingEnv passes sb3's check_env. Catches API mismatches
(wrong return shape, wrong dtype, missing methods) BEFORE training."""
from stable_baselines3.common.env_checker import check_env
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

md = load_market_data("train")
env = VNTradingEnv(md)
check_env(env, warn=True, skip_render_check=True)
print("OK env passes check_env")
PY
```

Expected: no exception, no warnings (or only render warnings). If warns
about `info` dict types, document — but DDPG doesn't care about info,
only obs+reward+done.

**Spike B — DDPG 1000-step smoke + reward inspection:**

```bash
.venv/bin/python <<'PY'
"""Train DDPG for 1000 steps on train split; verify no NaN in policy +
critic loss, and reward scale isn't absurd."""
import numpy as np
import torch
from stable_baselines3 import DDPG
from stable_baselines3.common.noise import NormalActionNoise
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

torch.manual_seed(42)
np.random.seed(42)

md = load_market_data("train")
env = VNTradingEnv(md)
n = env.action_space.shape[-1]
noise = NormalActionNoise(mean=np.zeros(n), sigma=0.1 * np.ones(n))
model = DDPG(
    "MlpPolicy", env,
    action_noise=noise,
    learning_starts=200,
    batch_size=64,
    learning_rate=1e-4,
    gamma=0.99,
    tau=0.005,
    verbose=0,
    seed=42,
)
model.learn(total_timesteps=1000, log_interval=100)

# Predict a few actions, check no NaN
obs, _ = env.reset(seed=42)
for _ in range(10):
    a, _ = model.predict(obs, deterministic=True)
    assert not np.any(np.isnan(a)), f"NaN action: {a}"
    obs, r, term, trunc, info = env.step(a)
    assert not np.isnan(r), "NaN reward"
    if term:
        break
print("OK DDPG 1000-step smoke (no NaN)")
PY
```

Expected: completes in ~30-60s, no NaN. If NaN → reward scaling issue
(D8); raise scale to 1000× and retry.

**Spike C — Reproducibility (same seed → same model):**

```bash
.venv/bin/python <<'PY'
"""Train DDPG twice with same seed, verify identical first-prediction action."""
import numpy as np, torch
from stable_baselines3 import DDPG
from stable_baselines3.common.noise import NormalActionNoise
from src.env_data_loader import load_market_data
from src.trading_env import VNTradingEnv

def train_once():
    torch.manual_seed(42); np.random.seed(42)
    md = load_market_data("train")
    env = VNTradingEnv(md)
    n = env.action_space.shape[-1]
    noise = NormalActionNoise(mean=np.zeros(n), sigma=0.1 * np.ones(n))
    m = DDPG("MlpPolicy", env, action_noise=noise, learning_starts=100,
             batch_size=32, learning_rate=1e-4, verbose=0, seed=42)
    m.learn(total_timesteps=500)
    obs, _ = env.reset(seed=42)
    return m.predict(obs, deterministic=True)[0]

a1, a2 = train_once(), train_once()
np.testing.assert_allclose(a1, a2, atol=1e-5)
print(f"OK reproducibility: a1={a1}, a2={a2}")
PY
```

If this fails: torch/numpy seed leak somewhere. Won't break the package
but flag in PR as "PKG-S note: full repro needs more work".

### Patterns to Follow

**RLAgent class shape (mirror `src/llm/multi_agent/agent.py:67-100`):**

```python
class RLAgent:
    """Wraps an sb3 model. Agent Protocol implementation."""

    def __init__(
        self,
        model_path: Path,
        name: str = "ddpg",  # caller sets "ddpg" or "ppo"
        algo: type = None,    # DDPG or PPO; auto-detected from .zip
        deterministic: bool = True,
    ) -> None:
        from stable_baselines3 import DDPG, PPO
        # Auto-detect algorithm from saved model
        self._model = (algo or self._detect_algo(model_path)).load(str(model_path))
        self.name = name
        self.deterministic = deterministic

    def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
        action, _state = self._model.predict(obs, deterministic=self.deterministic)
        return np.asarray(action, dtype=np.float32)
```

**DivergenceCallback (the project-specific piece):**

```python
class DivergenceCallback(BaseCallback):
    """Abort training if NaN/Inf in loss or |Q| exceeds threshold."""

    def __init__(self, q_threshold: float = 1e6, n_violations_allowed: int = 100):
        super().__init__()
        self.q_threshold = q_threshold
        self.n_violations_allowed = n_violations_allowed
        self.violations = 0
        self.aborted_reason: str | None = None

    def _on_step(self) -> bool:
        # Inspect model.logger (sb3 logs critic_loss + actor_loss + train/critic_loss)
        logger_dict = dict(self.model.logger.name_to_value)
        for key in ("train/critic_loss", "train/actor_loss"):
            v = logger_dict.get(key)
            if v is None:
                continue
            if not np.isfinite(v):
                self.aborted_reason = f"non-finite {key} = {v}"
                return False
        # Q-value monitoring (DDPG-specific)
        q_mean = logger_dict.get("train/q_value")  # set if available
        if q_mean is not None and abs(q_mean) > self.q_threshold:
            self.violations += 1
            if self.violations >= self.n_violations_allowed:
                self.aborted_reason = f"|Q| > {self.q_threshold} for {self.n_violations_allowed} steps"
                return False
        else:
            self.violations = 0  # reset on healthy step
        return True
```

**ValMetricsCallback (logs per-eval to JSONL):**

```python
class ValMetricsCallback(BaseCallback):
    """Periodic eval roll-out on val split; writes per-eval JSONL row."""

    def __init__(self, val_env, log_path, eval_freq=5000, n_eval_episodes=1):
        super().__init__()
        self.val_env = val_env
        self.log_path = Path(log_path)
        self.eval_freq = eval_freq
        self.n_eval_episodes = n_eval_episodes
        self.best_sharpe = -float("inf")
        self.best_save_path: Path | None = None

    def _on_step(self) -> bool:
        if self.n_calls % self.eval_freq != 0:
            return True
        cum_returns, sharpes = [], []
        for _ in range(self.n_eval_episodes):
            obs, _ = self.val_env.reset(seed=42)
            rewards = []
            done = False
            while not done:
                a, _ = self.model.predict(obs, deterministic=True)
                obs, r, term, trunc, _ = self.val_env.step(a)
                rewards.append(r)
                done = term or trunc
            cum_returns.append(sum(rewards))
            r = np.asarray(rewards)
            sharpes.append(float(r.mean() / (r.std() + 1e-8) * np.sqrt(252)))
        row = {
            "step": int(self.num_timesteps),
            "val_cum_return": float(np.mean(cum_returns)),
            "val_sharpe": float(np.mean(sharpes)),
        }
        # Append to JSONL
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        # Save best
        if row["val_sharpe"] > self.best_sharpe and self.best_save_path is not None:
            self.best_sharpe = row["val_sharpe"]
            self.model.save(str(self.best_save_path))
        return True
```

**Action noise decay (DDPG only):**

```python
class ActionNoiseDecayCallback(BaseCallback):
    """Linearly decay action_noise.sigma over training. sb3 doesn't auto-decay."""

    def __init__(self, sigma_start: float, sigma_end: float, total_timesteps: int):
        super().__init__()
        self.sigma_start = sigma_start
        self.sigma_end = sigma_end
        self.total_timesteps = total_timesteps

    def _on_step(self) -> bool:
        frac = min(self.num_timesteps / self.total_timesteps, 1.0)
        sigma = self.sigma_start + frac * (self.sigma_end - self.sigma_start)
        # sb3 NormalActionNoise: ._sigma is the per-dim array
        if self.model.action_noise is not None:
            self.model.action_noise._sigma = (
                self.model.action_noise._sigma * 0.0 + sigma
            )
        return True
```

**Error handling (CLAUDE.md alignment):**

- NaN in loss → `DivergenceCallback` aborts training, sets `aborted_reason`,
  CLI exits with code 2 + prints reason
- DDPG diverge → fall back to PPO is HUMAN decision: CLI exits 2 →
  operator runs `train_ppo.py`. Don't auto-trigger PPO in the same
  process (different model dirs, different seeds, different total_timesteps)
- Model load failure → CLI catches `OSError` + suggests
  `ls results/models/`; never propagates
- Eval roll-out fails (env error) → log warning, write `val_sharpe=NaN`
  in JSONL, continue training

---

## DESIGN DECISIONS — LOCK BEFORE IMPLEMENT

### D1. Shared `train_rl` core in `src/rl_training/core.py`

```python
def train_rl(
    algo_cls,           # DDPG or PPO
    cfg: dict,          # parsed YAML
    train_env_factory,  # () -> VecEnv-like
    val_env_factory,    # () -> Env
    total_timesteps: int,
    save_path: Path,
    log_path: Path,
    seed: int = 42,
    extra_callbacks: list[BaseCallback] | None = None,
) -> dict:
    """Returns summary dict {aborted, aborted_reason, best_sharpe, final_steps}."""
```

Why: 70% of DDPG and PPO trainer code overlaps (env factory, val callback,
divergence guard, JSONL logging). Extracting the shared core removes
duplication WITHOUT coupling — algo-specific args go through `cfg`.

### D2. Hyperparams in `configs/{ddpg,ppo}.yaml`

```yaml
# configs/ddpg.yaml
total_timesteps: 50000
learning_rate: 0.0001
buffer_size: 100000
learning_starts: 1000
batch_size: 128
tau: 0.005
gamma: 0.99
train_freq: 1
gradient_steps: 1
policy_kwargs:
  net_arch: [128, 128]
action_noise:
  sigma_start: 0.1
  sigma_end: 0.02
reward_scale: 100.0
eval_freq: 5000
n_eval_episodes: 1
divergence:
  q_threshold: 1.0e6
  n_violations_allowed: 100
```

```yaml
# configs/ppo.yaml
total_timesteps: 200000
learning_rate: 0.0003
n_steps: 2048
batch_size: 64
n_epochs: 10
gamma: 0.99
gae_lambda: 0.95
clip_range: 0.2
ent_coef: 0.0
vf_coef: 0.5
policy_kwargs:
  net_arch: [128, 128]
reward_scale: 1.0
eval_freq: 10000
n_eval_episodes: 1
```

Hyperparams from Xiong paper + sb3 defaults. Conservative budgets — full
train 50K/200K steps in ~30-60min CPU.

### D3. Action noise = `NormalActionNoise` with linear decay

Start σ=0.1 (10% of action range), end σ=0.02. Decay via
`ActionNoiseDecayCallback`. Why decay: early exploration matters,
late exploitation matters; sb3 doesn't auto-decay.

### D4. Best-on-val checkpoint via `ValMetricsCallback`

Save model when val Sharpe improves (NOT just cum_return — Sharpe
penalizes vol, more honest). Final exported model = best on val, NOT
last trained.

### D5. `DivergenceCallback` aborts training cleanly

NaN/Inf in critic_loss or actor_loss → abort immediately. |Q| > 1e6 for
100 consecutive steps → abort. Sets `aborted_reason` accessible to CLI
for exit code mapping.

### D6. `RLAgent` wraps sb3 model

Implements Agent Protocol. `decide()` calls `model.predict(obs,
deterministic=True)` returns action. `name` set by caller ("ddpg" or
"ppo"). Algo auto-detection via `.zip` filename heuristic + fallback to
trying DDPG then PPO load.

### D7. PPO backup is independent process, NOT auto-fallback

Issue #10 says "Q-value blow up → automatic fallback PPO log warning".
We interpret as: DDPG abort prints `WARNING: DDPG aborted (reason). Run
'scripts/train_ppo.py' for backup.` — operator triggers PPO. Reason: PPO
train is 30-60min; auto-running in same DDPG process would block + hide
the abort signal.

### D8. Reward scaling

DDPG: `reward_scale=100.0` (from yaml). PPO: `reward_scale=1.0`. Applied
via a thin `RewardScaleWrapper(env, scale)`. Scale only affects the
trainer; `RLAgent.decide()` is scale-agnostic. PKG-10 backtest measures
raw cumulative log-return on env reward (no scaling needed at eval).

### D9. Checkpoint every 10K steps + best-on-val

`EvalCallback` (sb3 built-in) handles checkpoint timing. Final model =
best on val. CLI prints final val Sharpe + path to model.

### D10. Training log = JSONL per-eval-interval

`ValMetricsCallback` writes one line per eval. Schema:

```json
{"step": 5000, "val_cum_return": 0.012, "val_sharpe": 0.34, "actor_loss": 0.123, "critic_loss": 0.045, "q_value_mean": 12.3}
```

PKG-10 + Person 1 read for learning curves.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — env wrapper + callbacks + config loader

**Tasks:**
- Add `PyYAML` to `pyproject.toml` (if missing)
- `src/rl_training/__init__.py` (exports)
- `src/rl_training/callbacks.py` — 3 callbacks (Divergence, ValMetrics, ActionNoiseDecay)
- `src/rl_training/core.py` — `train_rl` shared core + `RewardScaleWrapper`
- `configs/ddpg.yaml`, `configs/ppo.yaml`
- `tests/test_rl_callbacks.py` (~6 tests, mocked model + env)

### Phase 2: Algorithm-specific trainers

**Tasks:**
- `src/rl_training/ddpg_trainer.py` — `train_ddpg(cfg, ...)` instantiates DDPG
  with hyperparams + action noise + decay callback, calls `train_rl`
- `src/rl_training/ppo_trainer.py` — `train_ppo(cfg, ...)` instantiates PPO,
  calls `train_rl` (no action noise, no decay)

### Phase 3: Agent wrapper

**Tasks:**
- `src/agents/rl_agent.py` — `RLAgent(model_path, name)` implements Agent
  Protocol; `decide(obs, info)` calls `model.predict`
- `tests/test_rl_agent.py` (~5 tests: Protocol, save/load round-trip,
  predict shape, deterministic flag, dummy backtest)

### Phase 4: CLIs

**Tasks:**
- `scripts/train_ddpg.py` — load YAML, build env factories, call `train_ddpg`
- `scripts/train_ppo.py` — same with PPO
- `scripts/run_rl_backtest.py` — load model, wrap in `RLAgent`,
  `run_backtest(env, agent, seed)` → metrics + parquets

### Phase 5: Tests + smoke

**Tasks:**
- `tests/test_ddpg_smoke.py` — train 1000 steps on synthetic_market_data,
  verify no NaN + model save/load round-trip
- (Optional) Real-train DDPG full 50K steps on `train` split, eval on
  `val`. Capture training log + final val Sharpe. ~30-60min wallclock.

---

## STEP-BY-STEP TASKS

### 1. UPDATE `pyproject.toml` — add PyYAML

- **IMPLEMENT:** Add `"pyyaml>=6.0"` to `dependencies`. Run
  `.venv/bin/python -m pip install pyyaml` if missing.
- **VALIDATE:** `.venv/bin/python -c "import yaml; print(yaml.__version__)"`

### 2. RUN Spike A (env check_env)

- **VALIDATE:** prints `OK env passes check_env`

### 3. CREATE `configs/ddpg.yaml` + `configs/ppo.yaml`

- **IMPLEMENT:** Copy D2 spec verbatim
- **VALIDATE:** `.venv/bin/python -c "import yaml; print(yaml.safe_load(open('configs/ddpg.yaml')))"`

### 4. CREATE `src/rl_training/__init__.py`

- **IMPLEMENT:**
  ```python
  """RL training (PKG-9). DDPG primary + PPO backup, sb3-based."""
  from src.rl_training.core import RewardScaleWrapper, train_rl
  from src.rl_training.ddpg_trainer import train_ddpg
  from src.rl_training.ppo_trainer import train_ppo

  __all__ = ["train_rl", "train_ddpg", "train_ppo", "RewardScaleWrapper"]
  ```

### 5. CREATE `src/rl_training/callbacks.py`

- **IMPLEMENT:** 3 callbacks per D3/D4/D5 above. ~150 lines total.
- **PATTERN:** `stable_baselines3.common.callbacks.BaseCallback`; `_on_step`
  returns `False` to abort training cleanly.
- **GOTCHA:** sb3 `self.model.logger.name_to_value` is the live metrics dict;
  during `learning_starts` warm-up, train/* keys may be absent — guard
  with `.get(key)`.
- **VALIDATE:** import + smoke construct each callback

### 6. CREATE `src/rl_training/core.py`

- **IMPLEMENT:**
  ```python
  """Shared RL training core. DDPG/PPO trainers call train_rl() with their
  algo class + parsed config."""
  from __future__ import annotations

  import json
  import logging
  from pathlib import Path
  from typing import Any

  import gymnasium as gym
  import numpy as np
  from stable_baselines3.common.callbacks import BaseCallback, CallbackList

  from src.rl_training.callbacks import (
      ActionNoiseDecayCallback,
      DivergenceCallback,
      ValMetricsCallback,
  )

  log = logging.getLogger(__name__)


  class RewardScaleWrapper(gym.RewardWrapper):
      def __init__(self, env, scale: float = 1.0):
          super().__init__(env)
          self.scale = float(scale)

      def reward(self, reward):
          return float(reward) * self.scale


  def train_rl(
      algo_cls,
      algo_kwargs: dict,
      train_env,
      val_env,
      total_timesteps: int,
      save_path: Path,
      log_path: Path,
      divergence_q_threshold: float = 1e6,
      divergence_n_violations: int = 100,
      eval_freq: int = 5000,
      n_eval_episodes: int = 1,
      extra_callbacks: list[BaseCallback] | None = None,
      seed: int = 42,
  ) -> dict:
      save_path.parent.mkdir(parents=True, exist_ok=True)
      log_path.parent.mkdir(parents=True, exist_ok=True)
      if log_path.exists():
          log_path.unlink()  # fresh per-train log

      val_cb = ValMetricsCallback(
          val_env=val_env,
          log_path=log_path,
          eval_freq=eval_freq,
          n_eval_episodes=n_eval_episodes,
          best_save_path=save_path,
      )
      div_cb = DivergenceCallback(
          q_threshold=divergence_q_threshold,
          n_violations_allowed=divergence_n_violations,
      )
      callbacks = [val_cb, div_cb] + list(extra_callbacks or [])

      model = algo_cls(env=train_env, seed=seed, **algo_kwargs)
      try:
          model.learn(
              total_timesteps=total_timesteps,
              callback=CallbackList(callbacks),
          )
      except Exception as e:  # noqa: BLE001 — training never crashes the CLI
          log.warning("training raised %s: %s", type(e).__name__, e)
          return {
              "aborted": True,
              "aborted_reason": f"{type(e).__name__}: {e}",
              "best_sharpe": val_cb.best_sharpe,
              "final_step": int(model.num_timesteps),
          }

      return {
          "aborted": div_cb.aborted_reason is not None,
          "aborted_reason": div_cb.aborted_reason,
          "best_sharpe": val_cb.best_sharpe,
          "final_step": int(model.num_timesteps),
      }
  ```
- **GOTCHA #1:** `CallbackList` is the sb3 idiom for combining callbacks.
  Order matters only if callbacks read each other's state (ours don't).
- **GOTCHA #2:** Always-fresh log: delete `log_path` if exists; tests
  rely on per-call atomicity.
- **GOTCHA #3:** Bare `except Exception` is the explicit "don't crash CLI"
  contract — sb3 internal errors must surface as `aborted=True`, not stacktrace.

### 7. CREATE `src/rl_training/ddpg_trainer.py`

- **IMPLEMENT:**
  ```python
  """DDPG trainer (PKG-9). Wraps stable_baselines3.DDPG with project config."""
  from __future__ import annotations

  from pathlib import Path

  import numpy as np
  import yaml
  from stable_baselines3 import DDPG
  from stable_baselines3.common.noise import NormalActionNoise

  from src.rl_training.callbacks import ActionNoiseDecayCallback
  from src.rl_training.core import RewardScaleWrapper, train_rl


  def load_ddpg_config(cfg_path: Path) -> dict:
      return yaml.safe_load(cfg_path.read_text())


  def train_ddpg(
      cfg: dict,
      train_env,
      val_env,
      save_path: Path,
      log_path: Path,
      seed: int = 42,
  ) -> dict:
      reward_scale = float(cfg.get("reward_scale", 1.0))
      if reward_scale != 1.0:
          train_env = RewardScaleWrapper(train_env, scale=reward_scale)

      n_actions = train_env.action_space.shape[-1]
      noise_cfg = cfg.get("action_noise", {"sigma_start": 0.1, "sigma_end": 0.02})
      action_noise = NormalActionNoise(
          mean=np.zeros(n_actions),
          sigma=noise_cfg["sigma_start"] * np.ones(n_actions),
      )

      algo_kwargs = dict(
          policy="MlpPolicy",
          learning_rate=cfg["learning_rate"],
          buffer_size=cfg["buffer_size"],
          learning_starts=cfg["learning_starts"],
          batch_size=cfg["batch_size"],
          tau=cfg["tau"],
          gamma=cfg["gamma"],
          train_freq=cfg.get("train_freq", 1),
          gradient_steps=cfg.get("gradient_steps", 1),
          policy_kwargs=cfg.get("policy_kwargs", {}),
          action_noise=action_noise,
          verbose=cfg.get("verbose", 0),
      )

      total_timesteps = int(cfg["total_timesteps"])
      decay_cb = ActionNoiseDecayCallback(
          sigma_start=noise_cfg["sigma_start"],
          sigma_end=noise_cfg["sigma_end"],
          total_timesteps=total_timesteps,
      )

      return train_rl(
          algo_cls=DDPG,
          algo_kwargs=algo_kwargs,
          train_env=train_env,
          val_env=val_env,
          total_timesteps=total_timesteps,
          save_path=save_path,
          log_path=log_path,
          divergence_q_threshold=cfg.get("divergence", {}).get("q_threshold", 1e6),
          divergence_n_violations=cfg.get("divergence", {}).get("n_violations_allowed", 100),
          eval_freq=int(cfg.get("eval_freq", 5000)),
          n_eval_episodes=int(cfg.get("n_eval_episodes", 1)),
          extra_callbacks=[decay_cb],
          seed=seed,
      )
  ```

### 8. CREATE `src/rl_training/ppo_trainer.py`

- **IMPLEMENT:** Same shape as `ddpg_trainer.py`, swap `DDPG` → `PPO`, no
  action noise / decay callback. PPO algo_kwargs: `learning_rate, n_steps,
  batch_size, n_epochs, gamma, gae_lambda, clip_range, ent_coef, vf_coef,
  policy_kwargs`.

### 9. CREATE `src/agents/rl_agent.py`

- **IMPLEMENT:**
  ```python
  """RLAgent — Agent Protocol wrapper around a saved sb3 model."""
  from __future__ import annotations

  from pathlib import Path

  import numpy as np
  from stable_baselines3 import DDPG, PPO


  class RLAgent:
      """Loads a saved DDPG/PPO model and exposes Agent Protocol.

      Auto-detects algo from filename ("ddpg" → DDPG, "ppo" → PPO);
      falls back to DDPG.load if ambiguous.
      """

      def __init__(
          self,
          model_path: Path,
          name: str | None = None,
          algo: type | None = None,
          deterministic: bool = True,
      ) -> None:
          model_path = Path(model_path)
          if not model_path.exists():
              raise FileNotFoundError(f"model not found: {model_path}")
          self.model_path = model_path
          if algo is None:
              algo = self._detect_algo(model_path)
          self._algo = algo
          self._model = algo.load(str(model_path))
          self.name = name or model_path.stem.split("_")[0]
          self.deterministic = bool(deterministic)

      @staticmethod
      def _detect_algo(model_path: Path) -> type:
          stem = model_path.stem.lower()
          if "ddpg" in stem:
              return DDPG
          if "ppo" in stem:
              return PPO
          # Last resort: DDPG (could also try both, but explicit preferred)
          return DDPG

      def decide(self, obs: np.ndarray, info: dict) -> np.ndarray:
          action, _state = self._model.predict(obs, deterministic=self.deterministic)
          return np.asarray(action, dtype=np.float32)
  ```
- **GOTCHA:** `name` defaults to filename stem split on `_` — so
  `ddpg_best.zip` → `name="ddpg"`. Caller can override.

### 10. CREATE `tests/test_rl_callbacks.py` (~6 tests)

- **IMPLEMENT:**
  1. `test_divergence_callback_aborts_on_nan_loss` — mock model with logger
     containing `train/critic_loss=NaN`; `_on_step()` returns False
  2. `test_divergence_callback_aborts_on_q_threshold_exceeded` — feed Q > 1e6
     for n_violations_allowed steps; verify abort
  3. `test_divergence_callback_resets_violation_on_healthy_step` — feed
     Q > threshold once, then healthy Q → violations counter resets
  4. `test_val_metrics_callback_writes_jsonl_per_eval` — manually call
     `_on_step` at eval_freq; verify JSONL line written
  5. `test_val_metrics_callback_saves_best_on_sharpe_improvement` — simulate
     2 eval rolls with improving Sharpe; verify model.save called twice
     (use a fake model that records save() calls)
  6. `test_action_noise_decay_interpolates_linearly` — set total_timesteps=1000,
     start=0.1, end=0.02; at step 500 sigma should be ~0.06
- **PATTERN:** Mock `self.model` with `unittest.mock.Mock()` containing
  `.logger.name_to_value = {...}` + `.num_timesteps` + `.save()` recording.
- **VALIDATE:** `.venv/bin/pytest tests/test_rl_callbacks.py -v`

### 11. CREATE `tests/test_rl_agent.py` (~5 tests)

- **IMPLEMENT:**
  1. `test_rl_agent_implements_protocol` — train DDPG 200 steps on
     synthetic_market_data, save, load via RLAgent, `isinstance(.., Agent)`
  2. `test_decide_returns_valid_action_shape` — `decide(obs, info)` returns
     `np.ndarray, shape=(5,), dtype=float32`
  3. `test_save_load_round_trip` — save model, load via RLAgent, predict
     on same obs, action matches within 1e-5
  4. `test_algo_auto_detect_from_filename` — RLAgent("...ddpg_X.zip") uses
     DDPG; RLAgent("...ppo_X.zip") uses PPO
  5. `test_rl_agent_works_in_run_backtest` — full env loop with RLAgent
     (10 steps), no exception, returns valid `BacktestResult`
- **GOTCHA:** Real DDPG.fit on synthetic_market_data is slow (~10-30s for
  200 steps). Tests OK but flag with pytest marker if needed.
- **VALIDATE:** `.venv/bin/pytest tests/test_rl_agent.py -v`

### 12. CREATE `tests/test_ddpg_smoke.py` (~3 tests)

- **IMPLEMENT:**
  1. `test_ddpg_train_1000_steps_no_nan` — train_ddpg on synthetic env for
     1000 steps; verify `aborted=False`, model.zip exists, predict no NaN
  2. `test_ppo_train_1000_steps_no_nan` — same with PPO
  3. `test_divergence_callback_fires_with_pathological_reward` — wrap env
     with reward=NaN → DivergenceCallback aborts; CLI exit code logic
     verified
- **GOTCHA:** This test takes ~30-60s. Add to `slow` pytest marker if it
  exists, or accept the duration (acceptable for an RL smoke).
- **VALIDATE:** `.venv/bin/pytest tests/test_ddpg_smoke.py -v --timeout=180`

### 13. CREATE `scripts/train_ddpg.py`

- **IMPLEMENT:**
  ```python
  """CLI: train DDPG on train split, eval on val. Saves best model + JSONL log.

  Usage:
      .venv/bin/python scripts/train_ddpg.py                      # full train
      .venv/bin/python scripts/train_ddpg.py --total-timesteps 5000  # smoke
  """
  from __future__ import annotations

  import argparse
  import logging
  import sys
  from pathlib import Path

  from src import config
  from src.env_data_loader import load_market_data
  from src.rl_training.ddpg_trainer import load_ddpg_config, train_ddpg
  from src.trading_env import VNTradingEnv

  CFG_PATH = config.PROJECT_ROOT / "configs" / "ddpg.yaml"
  MODEL_PATH = config.PROJECT_ROOT / "results" / "models" / "ddpg_best.zip"
  LOG_PATH = config.PROJECT_ROOT / "results" / "ddpg_training_log.jsonl"


  def main() -> int:
      logging.basicConfig(
          level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
      )
      p = argparse.ArgumentParser()
      p.add_argument("--config", default=str(CFG_PATH))
      p.add_argument("--total-timesteps", type=int, default=None,
                     help="Override config total_timesteps (smoke runs)")
      p.add_argument("--seed", type=int, default=42)
      args = p.parse_args()

      cfg = load_ddpg_config(Path(args.config))
      if args.total_timesteps is not None:
          cfg["total_timesteps"] = int(args.total_timesteps)

      train_md = load_market_data("train")
      val_md = load_market_data("val")
      train_env = VNTradingEnv(train_md)
      val_env = VNTradingEnv(val_md)
      print(f"train sessions: {len(train_md.dates)}, "
            f"val sessions: {len(val_md.dates)}, "
            f"timesteps: {cfg['total_timesteps']}")

      result = train_ddpg(
          cfg=cfg,
          train_env=train_env,
          val_env=val_env,
          save_path=MODEL_PATH,
          log_path=LOG_PATH,
          seed=args.seed,
      )
      print("\n=== Training summary ===")
      print(f"aborted:       {result['aborted']}")
      print(f"reason:        {result.get('aborted_reason')}")
      print(f"best_sharpe:   {result['best_sharpe']:.4f}")
      print(f"final_step:    {result['final_step']}")
      print(f"model saved:   {MODEL_PATH}")
      print(f"log:           {LOG_PATH}")
      if result["aborted"]:
          print("\nWARNING: training aborted. Run 'scripts/train_ppo.py' for backup.")
          return 2
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

### 14. CREATE `scripts/train_ppo.py`

- **IMPLEMENT:** Mirror `train_ddpg.py`, swap to PPO trainer + config + paths.

### 15. CREATE `scripts/run_rl_backtest.py`

- **IMPLEMENT:**
  ```python
  """CLI: load trained RLAgent, run backtest on test split. Writes parquets."""
  from __future__ import annotations

  import argparse
  import sys
  from pathlib import Path

  from src import config
  from src.agent_base import BacktestResult
  from src.agents.rl_agent import RLAgent
  from src.baselines import _records_to_frames, _snapshot, run_backtest
  from src.env_data_loader import load_market_data
  from src.trading_env import VNTradingEnv

  RESULTS_DIR = config.PROJECT_ROOT / "results"


  def main() -> int:
      p = argparse.ArgumentParser()
      p.add_argument("--model", required=True, type=Path,
                     help="path to saved sb3 .zip")
      p.add_argument("--split", default="test", choices=["train", "val", "test"])
      p.add_argument("--seed", type=int, default=42)
      args = p.parse_args()

      md = load_market_data(args.split)
      env = VNTradingEnv(md)
      agent = RLAgent(args.model)
      print(f"agent: {agent.name}, model: {args.model}, "
            f"sessions: {len(md.dates)}")

      result = run_backtest(env, agent, seed=args.seed)
      out_dir = RESULTS_DIR / agent.name
      out_dir.mkdir(parents=True, exist_ok=True)
      result.portfolio_curve.to_parquet(
          out_dir / "portfolio_curve.parquet",
          engine="pyarrow", compression="snappy"
      )
      result.holdings_curve.to_parquet(
          out_dir / "holdings.parquet", engine="pyarrow", compression="snappy"
      )

      cum = result.final_pv / float(config.INITIAL_CAPITAL) - 1
      print("\n=== Backtest summary ===")
      print(f"agent:       {result.agent_name}")
      print(f"steps:       {result.n_steps}")
      print(f"final pv:    {result.final_pv:,.0f} VND")
      print(f"cum return:  {cum:+.2%}")
      print(f"saved:       {out_dir}/")
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

### 16. RUN smoke training (DDPG 5000 steps, PPO 5000 steps)

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/train_ddpg.py --total-timesteps 5000
  .venv/bin/python scripts/train_ppo.py --total-timesteps 5000
  ```
- **EXPECTED:** Both complete in 5-10 min, no abort, models saved.
- **CHECK:** `wc -l results/*_training_log.jsonl` shows ≥ 1 eval row each.

### 17. (Optional, blocking for PR sign-off) FULL train

- **IMPLEMENT:**
  ```bash
  .venv/bin/python scripts/train_ddpg.py        # 50K steps, ~30-45 min
  .venv/bin/python scripts/train_ppo.py         # 200K steps, ~30-60 min
  .venv/bin/python scripts/run_rl_backtest.py --model results/models/ddpg_best.zip
  .venv/bin/python scripts/run_rl_backtest.py --model results/models/ppo_best.zip
  ```
- **EXPECTED:**
  - DDPG val Sharpe ≥ -0.5 (acceptance criterion)
  - If DDPG aborts: CLI exits 2, run PPO instead — paste log into PR
  - Both backtests on test split produce parquets

### 18. Final ruff + full pytest

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/pytest tests/ -v
# Expected: ruff clean, ~186 tests pass (172 prior + ~14 new)
```

---

## TESTING STRATEGY

### Unit Tests (~14 new across 3 files)

| File | Count | Focus |
|------|------:|-------|
| `test_rl_callbacks.py` | 6 | Divergence (NaN, Q-threshold, reset), ValMetrics (JSONL, best-on-Sharpe), ActionNoiseDecay (linear interp) |
| `test_rl_agent.py` | 5 | Protocol, action shape, save/load round-trip, algo auto-detect, run_backtest integration |
| `test_ddpg_smoke.py` | 3 | DDPG 1000-step no NaN, PPO 1000-step no NaN, divergence fires with bad reward |

Total after PKG-9: **172 (current) + 14 = ~186 tests**.

### Integration smoke (manual, in PR description)

`scripts/train_ddpg.py --total-timesteps 5000` AND
`scripts/train_ppo.py --total-timesteps 5000`. Capture:
- Wall duration (5-15 min each)
- Final val Sharpe (sanity, just non-NaN)
- Model size (.zip ~ a few MB)
- JSONL log row count

### Edge Cases Explicitly Covered

| # | Edge case | Test |
|---|-----------|------|
| 1 | Critic loss → NaN mid-train | callbacks #1 |
| 2 | Q-value exceeds threshold | callbacks #2, #3 |
| 3 | Healthy step resets violation counter | callbacks #3 |
| 4 | ValMetricsCallback writes per eval | callbacks #4 |
| 5 | Best-on-val saving fires only on improvement | callbacks #5 |
| 6 | Action noise sigma decays linearly | callbacks #6 |
| 7 | DDPG abort surfaces in CLI exit code | smoke #3 + CLI manual |
| 8 | Save → Load round-trip preserves predictions | agent #3 |
| 9 | Algo auto-detect from filename | agent #4 |
| 10 | RLAgent fully compatible with run_backtest | agent #5 |

### Edge Cases NOT Covered (deferred)

- **Multi-seed variance** — PRD §13 future work, post-MVP
- **GPU acceleration** — torch detected CPU; we accept ~30-60min CPU train.
- **Full validation Sharpe** — observed value after full train is captured
  in PR description, not asserted in tests (val Sharpe depends on
  hyperparams + seed; flaky to assert exact number)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/rl_training/ src/agents/ tests/test_rl_*.py tests/test_ddpg_smoke.py scripts/train_*.py scripts/run_rl_backtest.py
```

### Level 2: Unit Tests

```bash
.venv/bin/pytest tests/test_rl_callbacks.py tests/test_rl_agent.py tests/test_ddpg_smoke.py -v --timeout=180
```

### Level 3: Full regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
# Expected: ~186 passed
```

### Level 4: CLI mocked smoke (no train)

```bash
.venv/bin/python scripts/train_ddpg.py --help
.venv/bin/python scripts/train_ppo.py --help
.venv/bin/python scripts/run_rl_backtest.py --help
# Expected: argparse helps print without exception
```

### Level 5: Smoke train (gated, ~10 min, 5000 steps)

```bash
.venv/bin/python scripts/train_ddpg.py --total-timesteps 5000
.venv/bin/python scripts/train_ppo.py --total-timesteps 5000
ls -la results/models/
wc -l results/*_training_log.jsonl
```

### Level 6: Full train (manual, ~1-2 hr total)

```bash
.venv/bin/python scripts/train_ddpg.py
.venv/bin/python scripts/train_ppo.py
.venv/bin/python scripts/run_rl_backtest.py --model results/models/ddpg_best.zip --split test
.venv/bin/python scripts/run_rl_backtest.py --model results/models/ppo_best.zip --split test
```

---

## ACCEPTANCE CRITERIA

Mirrors GitHub Issue #10:

- [ ] **DDPG train xong, val Sharpe ≥ -0.5** — verified by Level 6 manual full train
- [ ] **Q-value blow up → automatic fallback PPO + log warning** — divergence
  guard fires; CLI exit 2 prints "run train_ppo.py". (Interpretation: PPO
  is operator-triggered fallback, not in-process — see D7.)
- [ ] **Models saved at `results/models/{ddpg,ppo}_best.zip`** — verified
  by Level 5 + 6
- [ ] `RLAgent` implements `Agent` Protocol (test #1)
- [ ] Save/load round-trip preserves predictions (test #3)
- [ ] Per-eval JSONL log written (callback test #4)
- [ ] Divergence guard fires on NaN loss (callback test #1)
- [ ] Divergence guard fires on Q-threshold breach (callback test #2)
- [ ] Action noise decays linearly (callback test #6)
- [ ] ~14 new tests pass; 172 prior tests still pass; ruff clean

---

## COMPLETION CHECKLIST

- [ ] Spike A `check_env` passes; Spike B 1000-step DDPG no NaN;
      Spike C 2-run reproducibility within 1e-5
- [ ] `configs/ddpg.yaml`, `configs/ppo.yaml` written + parseable
- [ ] `src/rl_training/` module 5 files
- [ ] `src/agents/rl_agent.py` written; Protocol satisfied
- [ ] 3 CLIs written; `--help` works for each
- [ ] ~14 new tests pass; ruff clean
- [ ] Smoke train 5000 steps both algos; models saved; logs non-empty
- [ ] (Optional, recommended) Full train captured in PR description
- [ ] PR opened `PKG-9: DDPG trainer + PPO backup`, body `Closes #10`
- [ ] CLAUDE.md commit attribution rule followed (no AI co-author)
- [ ] PKG-10 unblocked (`RLAgent` constructible)

---

## NOTES

### Design decisions worth flagging in PR

1. **Module split `src/rl_training/`** — diverges from PRD scaffolding hint
   (`src/ddpg_trainer.py` flat). Reason: 70% trainer code overlap; flat
   files become duplicate or coupled. Module mirrors `src/llm/multi_agent/`
   pattern (PKG-8) which proved clean.
2. **`RLAgent` in `src/agents/`** — Issue #10 doesn't specify location;
   PRD §6 lists `src/agents/__init__.py` (registry, PKG-S). RLAgent goes
   in a sibling file `src/agents/rl_agent.py` so PKG-S can register it
   without merge conflict.
3. **Reward scaling 100× for DDPG only** — Q-network targets need
   reasonable magnitude; log-return × 100 ≈ unit scale. PPO doesn't need
   it (clip-ratio handles scale).
4. **Action noise sigma decay** — sb3 doesn't auto-decay. Custom callback
   linearly interpolates from `sigma_start` to `sigma_end` over training.
5. **PPO backup as operator-triggered** — CLI exit 2 + warning, not
   in-process auto-fallback. Reason: same model dir, same seed, same
   total_timesteps would alias; operator inspects DDPG abort log and
   runs PPO deliberately.
6. **Algo auto-detect by filename** — `RLAgent("...ddpg_best.zip")` picks
   DDPG. Heuristic-based but covers the only filename pattern we emit.

### Risks specific to PKG-9

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | DDPG diverges on first full run | PPO backup ready; CLI exit 2 fires; full PR description captures DDPG abort + PPO success |
| 2 | Train wall-time blows out deadline (CPU only) | Total 50K steps DDPG ~30-45 min; 200K PPO ~45-60 min; well under 1 day budget |
| 3 | reward_scale tuning needs iteration | Start at 100× (Xiong); if NaN, raise to 1000× per Spike B; document in PR |
| 4 | Action space half-wasted by long-only clamp | Acceptable for PKG-9; future work could clip actor output to [0,1] via custom policy |
| 5 | Val Sharpe < -0.5 (acceptance breach) | Issue criterion is "sanity, not good"; even random policies typically meet -0.5; if breached, log + retry with different seed |
| 6 | sb3 / gymnasium version drift breaks env | Spike A `check_env` catches at start; both deps already pinned in pyproject.toml |

### Khi gặp blocker

- DDPG aborts at step 100 with NaN critic loss → reward scale too small;
  bump `reward_scale` from 100 → 1000 in `configs/ddpg.yaml`
- DDPG aborts with |Q| explosion → buffer_size too small for learning_starts;
  raise buffer to 1M or lower learning_starts to 500
- PPO trains but val Sharpe = NaN → val rollout crashes; check
  `ValMetricsCallback._on_step` exception handling
- RLAgent prediction returns NaN at backtest time → model trained on
  different obs shape; verify env produces 56-dim obs (PKG-3 contract)
- Tests pass but real train aborts → likely env-specific divergence;
  inspect `ddpg_training_log.jsonl` for trajectory
- Full train takes > 2 hours → drop total_timesteps to 25K (DDPG) /
  100K (PPO); document in PR

### Phase 2 status after PKG-9

| PKG | Status |
|-----|--------|
| PKG-5 LLM core | ✅ merged |
| PKG-6 zero-shot | ✅ merged |
| PKG-7 single-agentic | ✅ merged |
| PKG-8 multi-agent | ✅ merged |
| **PKG-9 DDPG + PPO (this PR)** | 🟡 ready after impl |
| PKG-10 backtest engine | unblocked; all 4 agent types available |
| CHECKPOINT 24/05 | 8 days out; on track |

---

## Confidence Score

**7.5/10** for one-pass implementation.

Subtract:
- −0.5 DDPG-on-custom-env first run failure is empirically common; may
  need 1-2 reward_scale iterations
- −0.5 sb3 callback patterns are well-documented but our 3 custom
  callbacks are first-of-kind in this codebase
- −0.5 Wall-time uncertain on CPU torch; 50K DDPG could take 45-90min
- −0.5 Full validation depends on real-train results — can't validate
  in unit tests alone

Add back:
- +1.0 sb3 is battle-tested; gymnasium env already validated (PKG-3 +
  Spike A)
- +0.5 PKG-7/8 patterns (CLI shape, Agent wrapper, JSONL audit) transfer
  directly
- +0.5 PPO backup means the package can ship even if DDPG never converges

PKG-9 is the most empirically uncertain package because RL training is
inherently noisier than LLM API calls. The plan over-specifies divergence
guards + PPO backup so that "DDPG doesn't converge in 2 hours" is a
known-outcome path (operator triggers PPO), not a planning failure.
