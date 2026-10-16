"""Strict, advisory NV-S1 trusted-probe contracts. No runtime or receipt authority."""

from __future__ import annotations

import importlib.metadata
import json
import math
import random
import re
import statistics
import struct
import sys
from pathlib import Path

from service.artifacts import canonical_bytes, digest_bytes, digest_json

SCHEMA = "nv-s1-trusted-rmsnorm-probe-v1"
ARMS = ("eager", "pytorch_rms_norm")
SOURCE_FILES = (
    "compute/gpu_contract.py", "compute/rmsnorm_cuda.py", "compute/rmsnorm.py",
    "compute/attention.py", "compute/cuda_benchmark.py", "service/execution.py", "service/artifacts.py",
)
ROOT = Path(__file__).resolve().parents[1]


def _json_owned(value, cap=1048576):
    def visit(item, depth=0):
        if depth > 20:
            raise ValueError("JSON nesting limit")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("exact finite JSON values required")
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite JSON value")
    visit(value)
    try:
        raw = canonical_bytes(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid finite JSON") from exc
    if len(raw) > cap:
        raise ValueError("JSON byte limit")
    return json.loads(raw)


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"{name} requires exactly {sorted(expected)}")


def _integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} requires integer {lower}..{upper}")
    return value


def _positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid digest")
    return value


def strict_json_loads(raw, *, cap=1048576):
    if type(raw) is not bytes or len(raw) > cap:
        raise ValueError("bounded JSON bytes required")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite JSON literal")
    try:
        return _json_owned(json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                                      parse_constant=nonfinite), cap)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("malformed JSON") from exc


def probe_contract():
    """Return detached fixed policy, not an execution permission or measurement."""
    return {
        "schema": SCHEMA, "fixture_generator": "stdlib-random-fp32-le-v1",
        "arms": list(ARMS), "dtype": "float32", "epsilon": 1e-5, "atol": 1e-5, "rtol": 1e-4,
        "inference_only": True, "timed_shapes": [[1, 33], [64, 4096]],
        "warmup_per_arm": 10, "matched_pairs": 30, "aa_pairs": 10,
        "aa_ratio_interval": [0.90, 1.10], "one_call_per_sample": True,
        "allocator_policy": "warm_cache; output_released_before_next_call; no_empty_cache",
        "device_metric": "device_elapsed_ms: CUDA event interval around full queued arm",
        "component_metric": "component_elapsed_ns: dispatch allocation execution sync instrumentation",
        "excluded_from_timing": ["process_startup", "upload", "cpu_oracle", "output_download", "checking"],
        "cpu_threads": 1, "generated_execution": False, "performance_acceptance": False,
        "paid_execution": False, "physical_retirement_authority": False,
    }


def validate_probe_config(config):
    result = _json_owned(config, 65536)
    _keys(result, ("schema", "mode", "paid_execution", "device", "host", "seed"), "config")
    if result["schema"] != SCHEMA or result["mode"] != "trusted_authored":
        raise ValueError("unsupported probe schema/mode")
    if result["paid_execution"] is not False:
        raise ValueError("paid execution disabled")
    device = result["device"]
    _keys(device, ("uuid", "partition", "sharing", "reservation"), "device")
    if (type(device["uuid"]) is not str or re.fullmatch(
            r"GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", device["uuid"]) is None):
        raise ValueError("canonical physical GPU UUID required")
    if device["partition"] != "whole_gpu" or device["sharing"] != "exclusive_operator_declared":
        raise ValueError("whole physical GPU/operator declaration required; no MIG/MPS")
    if device["reservation"] != "whole_device_capacity":
        raise ValueError("whole capacity reservation required; no hard VRAM quota")
    _keys(result["host"], ("deadline_seconds", "max_output_bytes"), "host")
    _integer(result["host"]["deadline_seconds"], 1, 600, "deadline")
    _integer(result["host"]["max_output_bytes"], 1024, 1048576, "output cap")
    _integer(result["seed"], 0, 2147483647, "seed")
    return result


def _fixture_bytes(seed):
    """Exact little-endian FP32 CPU fixtures; neither CUDA arm participates."""
    rng = random.Random(seed)
    fixtures = []
    def add(name, rows, width, x, scale):
        fixtures.append({"id": name, "shape": [rows, width],
                         "x": struct.pack(f"<{rows * width}f", *x),
                         "scale": struct.pack(f"<{width}f", *scale)})
    add("tiny_trace", 1, 3, [1, 2, 2], [2, -3, 0])
    add("zero_rows", 3, 3, [0] * 9, [-100, 0, 100])
    add("width_one", 3, 1, [0, 1e-4, -10000], [-2])
    add("epsilon_location", 1, 3, [1e-4, 2e-4, 2e-4], [2, -3, .5])
    for rows, width in ((2, 3), (5, 31), (1, 33), (4, 257), (64, 4096)):
        x = [rng.uniform(-10000, 10000) for _ in range(rows * width)]
        scale = [rng.uniform(-100, 100) for _ in range(width)]
        x[0], x[-1], scale[0], scale[-1] = 10000, -10000, 100, -100
        add(f"seeded_{rows}x{width}", rows, width, x, scale)
    # Fresh changed-input post-timing cases, never a public held-out claim.
    add("changed_1x33", 1, 33, [((i % 7) - 3) * .0001 for i in range(33)],
        [(-1 if i % 2 else 1) * (i + 1) for i in range(33)])
    return fixtures


def _fixture_record(fixture):
    inputs = {"shape": fixture["shape"], "dtype": "float32", "byte_order": "little",
              "x_digest": digest_bytes(fixture["x"]), "scale_digest": digest_bytes(fixture["scale"]),
              "x_bytes": len(fixture["x"]), "scale_bytes": len(fixture["scale"])}
    return {"id": fixture["id"], **inputs, "input_digest": digest_json(inputs)}


def _package_version():
    try:
        return importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        return None


def build_probe_plan(config):
    config = validate_probe_config(config)
    source_hashes = {name: digest_bytes((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    lock = ROOT / "uv.lock"
    body = {"schema": SCHEMA, "config": config, "config_digest": digest_json(config),
            "contract": probe_contract(), "contract_digest": digest_json(probe_contract()),
            "source_hashes": source_hashes, "lock_digest": digest_bytes(lock.read_bytes()) if lock.exists() else None,
            "python": sys.version, "pytorch": _package_version(),
            "fixtures": [_fixture_record(f) for f in _fixture_bytes(config["seed"])],
            "required_hardware_evidence": ["observed_uuid", "driver", "partition", "concurrency",
                                           "external_reservation", "health", "external_device_retirement"]}
    return {**body, "plan_digest": digest_json(body)}


def _validate_plan(plan):
    plan = _json_owned(plan)
    rebuilt = build_probe_plan(plan.get("config"))
    body = {key: value for key, value in plan.items() if key != "plan_digest"}
    if (plan.get("plan_digest") != digest_json(body) or
            canonical_bytes(plan) != canonical_bytes(rebuilt)):
        raise ValueError("source/config/fixture/policy/version plan identity mismatch")
    return plan


def _blank_observation(plan, *, status="not_run", origin="not_run", reason="execution disabled"):
    return {"schema": SCHEMA, "status": status, "origin": origin, "reason": reason,
            "plan_digest": plan["plan_digest"], "config_digest": plan["config_digest"],
            "contract_digest": plan["contract_digest"], "source_hashes": dict(plan["source_hashes"]),
            "lock_digest": plan["lock_digest"], "fallback": None, "generated_execution": False,
            "performance_acceptance": False, "paid_execution": False, "billing": "not_applicable_unmetered",
            "environment": {"python": plan["python"], "pytorch": plan["pytorch"],
                            "cuda_runtime": None, "driver": None, "gpu": None},
            "lifecycle": {"gpu_may_have_started": False, "synchronized_all_work": False,
                          "process_group_retired": False, "external_device_retirement": "unverified",
                          "health": "unverified", "reservation_reuse": "unverified"},
            "warmup_completed": {}, "checks": [], "samples": [], "failed_sample": None,
            "summaries": {}, "ratios": {}}


def _distribution(values):
    return {"count": len(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values), "spread": max(values) - min(values)}


def _sample_schedule(contract):
    for shape in contract["timed_shapes"]:
        for group, count in (("ab", contract["matched_pairs"]), ("aa", contract["aa_pairs"])):
            labels = list(ARMS) if group == "ab" else ["eager_a", "eager_b"]
            for pair in range(count):
                order = labels if pair % 2 == 0 else labels[::-1]
                for position, label in enumerate(order):
                    yield {"shape": list(shape), "group": group, "pair_index": pair, "position": position,
                           "order": list(order), "arm": label,
                           "implementation": label if group == "ab" else "eager"}


def validate_probe_observation(plan, observation):
    """Validate detached advisory data and derive summaries, never acceptance authority."""
    plan = _validate_plan(plan)
    observation = _json_owned(observation)
    expected = _blank_observation(plan)
    _keys(observation, expected, "observation")
    for name in ("schema", "plan_digest", "config_digest", "contract_digest", "source_hashes",
                 "lock_digest", "fallback", "generated_execution", "performance_acceptance", "paid_execution", "billing"):
        if type(observation[name]) is not type(expected[name]) or observation[name] != expected[name]:
            raise ValueError(f"observation identity/policy mismatch: {name}")
    if observation["status"] not in {"not_run", "unavailable", "rejected", "failed", "unknown", "measured_advisory"}:
        raise ValueError("unsupported observation status")
    if observation["origin"] not in {"not_run", "mock", "real_cuda"}:
        raise ValueError("unsupported observation origin")
    if type(observation["reason"]) is not str or len(observation["reason"]) > 4096:
        raise ValueError("bounded reason required")
    life = observation["lifecycle"]
    _keys(life, expected["lifecycle"], "lifecycle")
    for name in ("gpu_may_have_started", "synchronized_all_work", "process_group_retired"):
        if type(life[name]) is not bool:
            raise ValueError("lifecycle Boolean required")
    for name in ("external_device_retirement", "health", "reservation_reuse"):
        if life[name] != "unverified":
            raise ValueError("probe has no physical-retirement/health/reuse authority")
    env = observation["environment"]
    _keys(env, expected["environment"], "environment")
    if env["python"] != plan["python"] or env["pytorch"] != plan["pytorch"]:
        raise ValueError("Python/PyTorch version mismatch")
    for name in ("cuda_runtime", "driver"):
        if env[name] is not None and (type(env[name]) is not str or not env[name] or len(env[name]) > 128):
            raise ValueError("invalid environment version")
    gpu = env["gpu"]
    if gpu is not None:
        _keys(gpu, ("uuid", "name", "compute_capability", "total_bytes", "partition", "concurrency", "mps",
                    "reservation_enforcement"), "GPU")
        if gpu["uuid"] != plan["config"]["device"]["uuid"]:
            raise ValueError("observed/requested UUID mismatch")
        if type(gpu["name"]) is not str or not gpu["name"] or len(gpu["name"]) > 256:
            raise ValueError("GPU name required")
        if type(gpu["compute_capability"]) is not list or len(gpu["compute_capability"]) != 2:
            raise ValueError("compute capability required")
        for part in gpu["compute_capability"]:
            _integer(part, 0, 99, "compute capability")
        _integer(gpu["total_bytes"], 1, 2**64 - 1, "GPU total capacity")
        if gpu["partition"] not in {"whole_gpu_observed", "unverified"}:
            raise ValueError("MIG partition excluded")
        if gpu["concurrency"] not in {"no_known_contention_observed", "known_contention", "unknown"}:
            raise ValueError("concurrency state invalid")
        if gpu["mps"] not in {"absent_observed", "unverified"}:
            raise ValueError("MPS excluded")
        if gpu["reservation_enforcement"] != "unverified":
            raise ValueError("operator declaration does not enforce reservation")
    checks, samples = observation["checks"], observation["samples"]
    if type(checks) is not list or len(checks) > 1000 or type(samples) is not list or len(samples) > 320:
        raise ValueError("bounded checks/samples required")
    fixtures = {f["id"]: f for f in plan["fixtures"]}
    for check in checks:
        _keys(check, ("id", "fixture_id", "phase", "arm", "input_digest", "output_digest", "outcome",
                      "input_unchanged", "independent_storage", "oracle_version", "max_absolute_error"), "check")
        if check["fixture_id"] not in fixtures or check["input_digest"] != fixtures[check["fixture_id"]]["input_digest"]:
            raise ValueError("check input identity mismatch")
        if check["phase"] not in {"pre", "warmup", "sample", "post"} or check["arm"] not in ARMS:
            raise ValueError("check phase/arm invalid")
        if type(check["id"]) is not str or len(check["id"]) > 128:
            raise ValueError("bounded check identity")
        _digest(check["output_digest"])
        if check["oracle_version"] != "python-float64-fsum-v1" or check["outcome"] not in {"pass", "fail", "invalid"}:
            raise ValueError("check semantics invalid")
        for name in ("input_unchanged", "independent_storage"):
            if type(check[name]) is not bool:
                raise ValueError("check Boolean invalid")
        error = check["max_absolute_error"]
        if error is None and check["outcome"] in {"pass", "fail"}:
            raise ValueError("pass/fail numerical check requires finite error metric")
        if error is not None and (type(error) not in (int, float) or not math.isfinite(error) or error < 0):
            raise ValueError("check error invalid")
    if len({c["id"] for c in checks}) != len(checks):
        raise ValueError("duplicate check identity")
    schedule = list(_sample_schedule(plan["contract"]))
    check_map = {c["id"]: c for c in checks}
    for index, sample in enumerate(samples):
        _keys(sample, (*schedule[0], "check_id", "device_elapsed_ms", "component_elapsed_ns", "memory",
                       "device_uuid", "plan_digest", "input_digest", "units"), "sample")
        for name, value in schedule[index].items():
            if canonical_bytes(sample[name]) != canonical_bytes(value):
                raise ValueError("sample order/shape/arm mismatch")
        if sample["check_id"] not in check_map:
            raise ValueError("timed output check missing")
        check = check_map[sample["check_id"]]
        fixture = next(f for f in plan["fixtures"] if f["id"].startswith("seeded_") and f["shape"] == sample["shape"])
        if (check["phase"] != "sample" or check["fixture_id"] != fixture["id"] or
                check["arm"] != sample["implementation"] or sample["input_digest"] != fixture["input_digest"]):
            raise ValueError("timed output/fixture identity mismatch")
        if sample["device_uuid"] != plan["config"]["device"]["uuid"] or sample["plan_digest"] != plan["plan_digest"]:
            raise ValueError("sample device/plan mismatch")
        if sample["units"] != {"device": "ms", "component": "ns"}:
            raise ValueError("sample units mismatch")
        _positive(sample["device_elapsed_ms"], "device sample")
        _integer(sample["component_elapsed_ns"], 1, 2**63 - 1, "component sample")
        mem = sample["memory"]
        names = ("starting_allocated_bytes", "starting_reserved_bytes", "peak_allocated_bytes", "peak_reserved_bytes",
                 "incremental_peak_allocated_bytes", "incremental_peak_reserved_bytes")
        _keys(mem, names, "allocator memory")
        for name in names:
            _integer(mem[name], 0, 2**64 - 1, name)
        for kind in ("allocated", "reserved"):
            delta = mem[f"peak_{kind}_bytes"] - mem[f"starting_{kind}_bytes"]
            if delta < 0 or delta != mem[f"incremental_peak_{kind}_bytes"]:
                raise ValueError("allocator delta mismatch")
    if observation["status"] == "measured_advisory" and observation["failed_sample"] is not None:
        raise ValueError("complete measurement cannot contain a failed sample")
    if observation["failed_sample"] is not None:
        _keys(observation["failed_sample"], ("schedule", "stage", "reason"), "failed sample")
        if observation["failed_sample"]["schedule"] != (schedule[len(samples)] if len(samples) < len(schedule) else None):
            raise ValueError("failed sample schedule mismatch")
        for field in ("stage", "reason"):
            if type(observation["failed_sample"][field]) is not str or len(observation["failed_sample"][field]) > 4096:
                raise ValueError("bounded failed sample evidence")
    warmup = observation["warmup_completed"]
    if type(warmup) is not dict:
        raise ValueError("warmup map required")
    allowed_warm = {f"{r}x{h}:{arm}" for r, h in plan["contract"]["timed_shapes"] for arm in ARMS}
    if not set(warmup) <= allowed_warm:
        raise ValueError("unknown warmup key")
    for value in warmup.values():
        _integer(value, 0, 10, "warmup count")
    observation["summaries"], observation["ratios"] = {}, {}
    complete = observation["status"] == "measured_advisory"
    if complete:
        if observation["origin"] != "real_cuda":
            raise ValueError("mock data cannot produce real measurement verdict")
        if not all(life[name] for name in ("gpu_may_have_started", "synchronized_all_work", "process_group_retired")):
            raise ValueError("complete synchronized normal parent-observed completion required")
        if gpu is None or env["cuda_runtime"] is None or len(samples) != len(schedule):
            raise ValueError("complete CUDA metadata/sample count required")
        if set(warmup) != allowed_warm or any(value != 10 for value in warmup.values()):
            raise ValueError("complete warmup required")
        required = {(f["id"], phase, arm) for f in plan["fixtures"] for phase in ("pre", "post") for arm in ARMS}
        actual = {(c["fixture_id"], c["phase"], c["arm"]) for c in checks}
        if not required <= actual or len({s["check_id"] for s in samples}) != len(samples):
            raise ValueError("complete unique pre/post/timed checks required")
        for shape in plan["contract"]["timed_shapes"]:
            fixture_id = next(f["id"] for f in plan["fixtures"] if f["id"].startswith("seeded_") and f["shape"] == shape)
            for arm in ARMS:
                warms = [c for c in checks if c["phase"] == "warmup" and c["fixture_id"] == fixture_id and c["arm"] == arm]
                if len(warms) != 10:
                    raise ValueError("warmup output checks incomplete")
        if any(c["outcome"] != "pass" or not c["input_unchanged"] or not c["independent_storage"] for c in checks):
            raise ValueError("numerical/storage/input mutation gate failed")
    if observation["status"] in {"not_run", "unavailable", "rejected"} and (checks or samples or warmup or gpu or life["gpu_may_have_started"]):
        raise ValueError("unstarted state contains execution evidence")
    if observation["status"] == "not_run" and observation["origin"] != "not_run":
        raise ValueError("not-run origin required")
    if observation["origin"] == "not_run" and (checks or samples):
        raise ValueError("not-run cannot contain samples")
    if complete:
        for shape in plan["contract"]["timed_shapes"]:
            key = f"{shape[0]}x{shape[1]}"
            summary = {}
            for label in (*ARMS, "eager_a", "eager_b"):
                subset = [s for s in samples if s["shape"] == shape and s["arm"] == label]
                summary[label] = {metric: _distribution([s[metric] for s in subset])
                                  for metric in ("device_elapsed_ms", "component_elapsed_ns")}
            observation["summaries"][key] = summary
            aa = {metric: summary["eager_a"][metric]["median"] / summary["eager_b"][metric]["median"]
                  for metric in ("device_elapsed_ms", "component_elapsed_ns")}
            stable = all(.90 <= value <= 1.10 for value in aa.values())
            metadata = (env["driver"] is not None and gpu["partition"] == "whole_gpu_observed" and
                        gpu["concurrency"] == "no_known_contention_observed" and gpu["mps"] == "absent_observed")
            observation["ratios"][key] = {"numerator": "eager", "denominator": "pytorch_rms_norm",
                "aa_diagnostic": aa, "status": "unstable_measurement" if not stable else
                "matched_advisory" if metadata else "required_metadata_unverified",
                "device": summary["eager"]["device_elapsed_ms"]["median"] /
                summary["pytorch_rms_norm"]["device_elapsed_ms"]["median"] if stable and metadata else None,
                "component": summary["eager"]["component_elapsed_ns"]["median"] /
                summary["pytorch_rms_norm"]["component_elapsed_ns"]["median"] if stable and metadata else None}
    return _json_owned(observation)
