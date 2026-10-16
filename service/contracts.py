"""Validated, detached domain contracts. Inputs never become mutable authority."""

from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from typing import Any
from .artifacts import canonical_bytes, digest_json


class RuntimeErrorBase(Exception):
    """Expected domain rejection; API callers may safely classify it."""


class Conflict(RuntimeErrorBase):
    pass


class Fenced(RuntimeErrorBase):
    pass


class BudgetExceeded(RuntimeErrorBase):
    pass


class CapacityExceeded(RuntimeErrorBase):
    pass


class NotFound(RuntimeErrorBase):
    pass


class Unsupported(RuntimeErrorBase):
    pass


class ResetRequired(RuntimeErrorBase):
    def __init__(self, message: str, snapshot: dict | None = None):
        super().__init__(message)
        self.snapshot = snapshot


OWNER_FIELDS = (
    "service_incarnation",
    "tenant_id",
    "task_id",
    "generation",
    "node_id",
    "node_epoch",
    "attempt_id",
)


def freeze(value: Any) -> Any:
    """Return a JSON deep copy; reject non-JSON/nonfinite authority input."""
    return json.loads(canonical_bytes(value))


def strict_int(value: Any, name: str, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def identity(value: Any, name: str = "identity") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError(f"invalid {name}")
    return value


def digest(value: Any, name: str = "digest") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be SHA-256 hex")
    return value


def timestamp(value: Any, name: str) -> float:
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("timezone required")
            value = date.timestamp()
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError(f"invalid {name}") from exc
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite UTC timestamp")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite UTC timestamp") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite UTC timestamp")
    return value


def parse_json(data: str | bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite JSON number")
        return result

    return json.loads(
        data,
        object_pairs_hook=unique,
        parse_float=finite_float,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"nonfinite JSON: {x}")),
    )


CONTRACT_FIELDS = {
    "repo_id",
    "base_revision",
    "requirements",
    "capabilities",
    "execution_deadline",
    "review_deadline",
    "profile",
    "patch_slot_limit",
    "budget_units",
    "max_nodes",
    "max_attempts",
    "model",
    "grader_digest",
    "environment_digest",
    "rate_snapshot",
    "repair_spec",
    "schema",
}


def validate_contract(contract: dict, now: float | None = None) -> dict:
    if not isinstance(contract, dict):
        raise ValueError("contract must be an object")
    if set(contract) - CONTRACT_FIELDS:
        raise ValueError(f"unknown contract fields: {sorted(set(contract) - CONTRACT_FIELDS)}")
    result = freeze(contract)
    now = time.time() if now is None else now
    for name in ("repo_id", "base_revision"):
        if not isinstance(result.get(name), str) or not result[name] or len(result[name]) > 512:
            raise ValueError(f"{name} is required and bounded")
    requirements = result.get("requirements")
    if (
        not isinstance(requirements, list)
        or not requirements
        or len(requirements) > 128
        or any(not isinstance(x, str) or not x or len(x) > 8192 for x in requirements)
    ):
        raise ValueError("requirements must be a nonempty bounded list of strings")
    defaults = {
        "schema": 1,
        "capabilities": [],
        "execution_deadline": now + 3600,
        "review_deadline": now + 86400,
        "profile": "production",
        "patch_slot_limit": 2,
        "budget_units": 1000,
        "max_nodes": 32,
        "max_attempts": 3,
        "model": "scripted-fixture-v1",
        "grader_digest": digest_json("fixture-grader-v1"),
        "environment_digest": digest_json("trusted-local-v1"),
        "rate_snapshot": None,
    }
    for name, value in defaults.items():
        result.setdefault(name, value)
    strict_int(result["schema"], "schema", 1, 1)
    for name, lower, upper in (
        ("patch_slot_limit", 1, 4),
        ("budget_units", 0, 2**63 - 1),
        ("max_nodes", 1, 128),
        ("max_attempts", 1, 100),
    ):
        strict_int(result[name], name, lower, upper)
    if result["profile"] not in ("production", "research"):
        raise Unsupported("unsupported execution profile")
    if result["profile"] == "production" and result["patch_slot_limit"] > 2:
        raise Unsupported("production profile permits at most two patch slots")
    if result["profile"] == "research" and result["patch_slot_limit"] not in (1, 2, 4):
        raise Unsupported("research profile must select 1/2/4 slots")
    if (
        not isinstance(result["capabilities"], list)
        or len(result["capabilities"]) > 64
        or any(not isinstance(x, str) or not x or len(x) > 128 for x in result["capabilities"])
    ):
        raise ValueError("invalid capabilities")
    if not isinstance(result["model"], str) or not result["model"] or len(result["model"]) > 128:
        raise ValueError("invalid model")
    for name in ("grader_digest", "environment_digest"):
        digest(result[name], name)
    for name in ("execution_deadline", "review_deadline"):
        result[name] = timestamp(result[name], name)
    if result["review_deadline"] < result["execution_deadline"]:
        raise ValueError("review deadline precedes execution deadline")
    if result["rate_snapshot"] is not None and not isinstance(result["rate_snapshot"], dict):
        raise ValueError("rate_snapshot must be an object")
    if "repair_spec" in result:
        repair = result["repair_spec"]
        fields = {
            "schema", "input_digest", "repository_digest", "recipe_digest", "provider_digest",
            "max_turns", "max_worker_tests", "context_bytes",
        }
        if not isinstance(repair, dict) or set(repair) != fields:
            raise ValueError("complete supported repair specification required")
        strict_int(repair["schema"], "repair schema", 1, 1)
        for name in ("input_digest", "repository_digest", "recipe_digest", "provider_digest"):
            digest(repair[name], name)
        strict_int(repair["max_turns"], "repair max_turns", 1, 100)
        strict_int(repair["max_worker_tests"], "repair max_worker_tests", 1, 8)
        strict_int(repair["context_bytes"], "repair context_bytes", 1024, 1048576)
        if result["patch_slot_limit"] != 1:
            raise Unsupported("supported repository repair requires one patch slot")
    return result


def validate_owner(owner: dict) -> dict:
    if not isinstance(owner, dict) or any(name not in owner for name in OWNER_FIELDS):
        raise Fenced("incomplete ownership tuple")
    result = {name: owner[name] for name in OWNER_FIELDS}
    for name in ("generation", "node_epoch"):
        strict_int(result[name], name, 1)
    for name in set(OWNER_FIELDS) - {"generation", "node_epoch"}:
        identity(result[name], name)
    return result
