"""Optional immutable pending-work policy; database transactions own admission."""

from .artifacts import digest_json
from .contracts import Unsupported, freeze, strict_int


def validate_admission_policy(value):
    if not isinstance(value, dict) or set(value) != {
        "schema", "service_pending_limit", "tenant_pending_limit"
    }:
        raise ValueError("invalid admission policy")
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("unsupported admission policy")
    for key in ("service_pending_limit", "tenant_pending_limit"):
        strict_int(value[key], key, 1, 10000)
    if value["tenant_pending_limit"] > value["service_pending_limit"]:
        raise ValueError("tenant pending limit exceeds service limit")
    return freeze(value)


def persisted_admission_policy(guard):
    keys = {"admission_policy", "admission_policy_digest"}
    if not keys.intersection(guard):
        return None
    if not keys.issubset(guard):
        raise Unsupported("incomplete persisted admission policy")
    try:
        policy = validate_admission_policy(guard["admission_policy"])
    except ValueError as exc:
        raise Unsupported("invalid persisted admission policy") from exc
    if guard["admission_policy_digest"] != digest_json(policy):
        raise Unsupported("persisted admission policy integrity mismatch")
    return policy
