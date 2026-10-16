"""Offline action-only PPO arithmetic and policy lag metadata; no optimizer/training launch."""

import math
from dataclasses import dataclass
from statistics import mean

from evals.validation import count, finite_real


@dataclass(frozen=True)
class Trajectory:
    sampled_token_ids: tuple[int, ...]
    training_token_ids: tuple[int, ...]
    token_kinds: tuple[str, ...]
    action_mask: tuple[int, ...]
    behavior_logprobs: tuple[float, ...]
    current_logprobs: tuple[float, ...]
    behavior_policy_version: int
    current_policy_version: int
    model_revision: str
    tokenizer_revision: str
    environment_revision: str
    reward: float
    reward_provenance: str
    termination_reason: str

    def validate(self, *, max_policy_lag=0):
        n = len(self.sampled_token_ids)
        if not n or any(
            len(getattr(self, field)) != n
            for field in (
                "training_token_ids",
                "token_kinds",
                "action_mask",
                "behavior_logprobs",
                "current_logprobs",
            )
        ):
            raise ValueError("mismatched trajectory lengths")
        if self.sampled_token_ids != self.training_token_ids:
            raise ValueError("trainer tokens differ from actual sampled/observed sequence")
        for token in self.sampled_token_ids + self.training_token_ids:
            count(token, "token ID")
        for mask in self.action_mask:
            count(mask, "action mask")
        if any(k not in {"action", "observation", "padding"} for k in self.token_kinds):
            raise ValueError("invalid token kind")
        if self.action_mask != tuple(int(k == "action") for k in self.token_kinds):
            raise ValueError("action mask must exclude observations and padding exactly")
        for probabilities in (self.behavior_logprobs, self.current_logprobs):
            for probability in probabilities:
                finite_real(probability, "log probability")
                if probability > 0:
                    raise ValueError("log probability must be nonpositive")
        count(max_policy_lag, "max_policy_lag")
        count(self.behavior_policy_version, "behavior_policy_version")
        count(self.current_policy_version, "current_policy_version")
        if not 0 <= self.current_policy_version - self.behavior_policy_version <= max_policy_lag:
            raise ValueError("policy lag exceeds declared bound or current policy is older")
        if any(
            not isinstance(s, str) or not s
            for s in (
                self.model_revision,
                self.tokenizer_revision,
                self.environment_revision,
                self.reward_provenance,
                self.termination_reason,
            )
        ):
            raise ValueError("missing provenance")
        finite_real(self.reward, "reward")
        if (
            self.termination_reason in {"infrastructure_failed", "effect_unknown"}
            and self.reward_provenance != "explicit_infrastructure_reward_policy"
        ):
            raise ValueError("infrastructure/Unknown rewards require an explicit separate policy")


def masked_objective(trajectory, advantage, *, clip=0.2, max_policy_lag=0):
    trajectory.validate(max_policy_lag=max_policy_lag)
    finite_real(advantage, "advantage")
    finite_real(clip, "clip", minimum=0)
    if clip >= 1:
        raise ValueError("invalid clip")
    actions = [i for i, active in enumerate(trajectory.action_mask) if active]
    contributions = []
    for i in actions:
        try:
            ratio = math.exp(trajectory.current_logprobs[i] - trajectory.behavior_logprobs[i])
        except OverflowError as exc:
            raise ValueError("importance ratio overflow") from exc
        finite_real(ratio, "importance ratio", minimum=0)
        clipped = min(1 + clip, max(1 - clip, ratio))
        unclipped_value = finite_real(ratio * advantage, "unclipped objective")
        clipped_value = finite_real(clipped * advantage, "clipped objective")
        contributions.append(
            {
                "index": i,
                "token_id": trajectory.sampled_token_ids[i],
                "ratio": ratio,
                "unclipped": unclipped_value,
                "clipped": clipped_value,
                "loss": -min(unclipped_value, clipped_value),
            }
        )
    return {
        "evidence": "offline loss arithmetic, no gradient or training claim",
        "action_tokens": len(actions),
        "loss": mean(c["loss"] for c in contributions) if actions else 0.0,
        "zero_action_mask": not bool(actions),
        "contributions": contributions,
    }


def group_advantages(trajectories, *, max_policy_lag=0):
    if not trajectories:
        raise ValueError("empty reward group")
    for t in trajectories:
        t.validate(max_policy_lag=max_policy_lag)
    identities = {
        (
            t.behavior_policy_version,
            t.current_policy_version,
            t.model_revision,
            t.tokenizer_revision,
            t.environment_revision,
        )
        for t in trajectories
    }
    if len(identities) != 1:
        raise ValueError("mixed policy/environment/tokenizer versions in group")
    try:
        average = finite_real(mean(t.reward for t in trajectories), "mean reward")
        variance = finite_real(
            mean((t.reward - average) ** 2 for t in trajectories), "reward variance", minimum=0
        )
    except OverflowError as exc:
        raise ValueError("reward normalization overflow") from exc
    return {
        "mean_reward": average,
        "population_variance": variance,
        "zero_variance": variance == 0,
        "advantages": [
            0.0 if variance == 0 else (t.reward - average) / math.sqrt(variance) for t in trajectories
        ],
    }
