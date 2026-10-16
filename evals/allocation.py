"""Fixed-N dollar allowances; reservations and Unknown liabilities cannot be reclaimed."""

import copy
from dataclasses import dataclass, field
from decimal import Decimal

from .validation import count, finite_real


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("money must be a numeric nonboolean amount")
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError("money must be finite and nonnegative")
    return value


@dataclass
class WorkerAllowance:
    allowance: Decimal
    settled: Decimal = Decimal(0)
    reserved: Decimal = Decimal(0)
    unknown: Decimal = Decimal(0)

    @property
    def floor(self):
        return self.settled + self.reserved + self.unknown

    def validate(self):
        for attribute in ("allowance", "settled", "reserved", "unknown"):
            setattr(self, attribute, money(getattr(self, attribute)))
        if self.floor > self.allowance:
            raise ValueError("worker exposure exceeds allowance")


@dataclass
class Allocation:
    ceiling: Decimal
    reserves: dict[str, Decimal]
    workers: dict[str, WorkerAllowance]
    decisions: list[dict] = field(default_factory=list)

    @classmethod
    def static(cls, ceiling, n, reserves):
        count(n, "worker count", 1)
        if n not in (1, 2, 4) or set(reserves) != {"coordinator", "integration", "verification", "cleanup"}:
            raise ValueError("explicit reserves and fixed N=1/2/4 required")
        ceiling = money(ceiling)
        reserves = {k: money(v) for k, v in reserves.items()}
        remaining = ceiling - sum(reserves.values())
        if remaining < 0:
            raise ValueError("reserves exceed ceiling")
        result = cls(ceiling, reserves, {f"worker_{i}": WorkerAllowance(remaining / n) for i in range(n)})
        result.validate()
        return result

    def validate(self):
        self.ceiling = money(self.ceiling)
        self.reserves = {k: money(v) for k, v in self.reserves.items()}
        for worker in self.workers.values():
            worker.validate()
        if sum(w.allowance for w in self.workers.values()) + sum(self.reserves.values()) > self.ceiling:
            raise ValueError("aggregate allowance exceeds ceiling")

    def observe_exposure(self, worker_id, *, settled, reserved, unknown):
        previous = self.workers[worker_id]
        candidate = WorkerAllowance(previous.allowance, money(settled), money(reserved), money(unknown))
        candidate.validate()
        if candidate.settled < previous.settled:
            raise ValueError(
                "cumulative settled spend cannot decrease; refunds need a separate unsupported protocol"
            )
        self.workers[worker_id] = candidate

    def progress_aware(self, observations, decision_time):
        """Only observed complete/failed donors free safe unused funds; unmet work competes by need."""
        finite_real(decision_time, "decision_time", minimum=0)
        if len(observations) != len(self.workers):
            raise ValueError("one observation per worker at a nonnegative decision time")
        observed = {}
        for observation in observations:
            worker = observation["worker_id"]
            if (
                worker not in self.workers
                or worker in observed
                or not isinstance(observation.get("observation_id"), str)
                or not observation["observation_id"]
            ):
                raise ValueError("missing/duplicate observation identity")
            finite_real(observation["observed_at"], "observed_at", minimum=0)
            if observation["observed_at"] > decision_time:
                raise ValueError("future or invalid observation")
            if observation["state"] not in {"running", "blocked", "complete", "failed"}:
                raise ValueError("invalid observed state")
            money(observation["estimated_remaining_usd"])
            observed[worker] = observation
        previous = {k: str(w.allowance) for k, w in self.workers.items()}
        pool = self.reserves.pop("unallocated", Decimal(0))
        for worker, observation in observed.items():
            if observation["state"] in {"complete", "failed"}:
                w = self.workers[worker]
                pool += w.allowance - w.floor
                w.allowance = w.floor
        recipients = sorted(
            (k for k, o in observed.items() if o["state"] == "running"),
            key=lambda k: (-money(observed[k]["estimated_remaining_usd"]), k),
        )
        for worker in recipients:
            w = self.workers[worker]
            needed = max(
                Decimal(0), money(observed[worker]["estimated_remaining_usd"]) - (w.allowance - w.floor)
            )
            grant = min(needed, pool)
            w.allowance += grant
            pool -= grant
        # Keep unused pool as an explicit reserve; never silently increase worker ceilings.
        self.reserves["unallocated"] = self.reserves.get("unallocated", Decimal(0)) + pool
        self.validate()
        record = {
            "decision_time": decision_time,
            "observation_ids": [observed[k]["observation_id"] for k in sorted(observed)],
            "previous": previous,
            "new": {k: str(w.allowance) for k, w in self.workers.items()},
            "reserves": {k: str(v) for k, v in self.reserves.items()},
            "reason": "Reclaim only unused completed/failed allowance; retain settled, reserved and Unknown floors; serve running need with deterministic ties.",
        }
        self.decisions.append(copy.deepcopy(record))
        return record
