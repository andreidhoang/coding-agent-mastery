"""Authored RMSNorm CUDA readiness probe; execution opt-in, advisory data only.

Default invocation constructs a CPU-only immutable plan. The hardware branch is
prepared, never silently substituted by CPU/MPS, and accepts no candidate code.
"""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path
import sys
import time

from service.artifacts import canonical_bytes, digest_bytes
from service.execution import bounded_process

from .gpu_contract import (
    ARMS, ROOT, _blank_observation, _fixture_bytes, _fixture_record, _sample_schedule, _validate_plan,
    build_probe_plan, strict_json_loads, validate_probe_config, validate_probe_observation,
)


class _NumericalFailure(Exception):
    pass


class _CudaUncertainty(Exception):
    pass


def _tensor_bytes(tensor):
    # Logical bytes, preserving signed zeros; no optional numpy dependency.
    return bytes(tensor.detach().resolve_neg().contiguous().reshape(-1).view(__import__("torch").uint8).tolist())


def _eager_arm(torch, x, scale):
    return (x / torch.sqrt((x * x).mean(dim=1, keepdim=True) + 1e-5) * scale).contiguous()


def _library_arm(torch, x, scale):
    return torch.nn.functional.rms_norm(x, (x.shape[1],), weight=scale, eps=1e-5)


class _CudaBackend:
    """Trusted fixed host, authored arms, selected device/stream, no custom loader."""

    origin = "real_cuda"

    def __init__(self, torch, plan, observation):
        self.torch, self.plan, self.observation = torch, plan, observation
        self.device = torch.device("cuda:0")  # Visibility is pinned to one requested physical UUID.
        self.stream = torch.cuda.Stream(device=self.device)
        self.inputs = {}
        self.cpu = {}
        self.references = {}
        torch.set_num_threads(1)

    def sync(self):
        try:
            self.torch.cuda.synchronize(self.device)
        except Exception as exc:
            raise _CudaUncertainty("CUDA synchronization failed") from exc

    def prepare(self, fixtures):
        from .rmsnorm import rmsnorm_reference
        torch = self.torch
        # All CPU inputs/references are complete before any timed work.
        for fixture in fixtures:
            r, h = fixture["shape"]
            x = torch.tensor(struct.unpack(f"<{r*h}f", fixture["x"]), dtype=torch.float32).reshape(r, h)
            scale = torch.tensor(struct.unpack(f"<{h}f", fixture["scale"]), dtype=torch.float32)
            self.cpu[fixture["id"]] = (x, scale)
            self.references[fixture["id"]] = rmsnorm_reference(x, scale)
        for fixture in fixtures:
            x, scale = self.cpu[fixture["id"]]
            self.observation["lifecycle"]["gpu_may_have_started"] = True
            with torch.cuda.stream(self.stream):
                self.inputs[fixture["id"]] = (x.to(self.device), scale.to(self.device))
        self.sync()

    def call(self, arm, fixture):
        torch = self.torch
        x, scale = self.inputs[fixture["id"]]
        self.observation["lifecycle"]["gpu_may_have_started"] = True
        with torch.inference_mode(), torch.cuda.stream(self.stream):
            return (_eager_arm if arm == "eager" else _library_arm)(torch, x, scale)

    def check(self, output, arm, fixture, phase, check_id):
        from .rmsnorm import check_rmsnorm
        torch = self.torch
        x, scale = self.inputs[fixture["id"]]
        cpu_x, cpu_scale = self.cpu[fixture["id"]]
        independent = True
        if type(output) is not torch.Tensor or output.is_nested or output.layout != torch.strided:
            raise _NumericalFailure("arm did not return an exact dense tensor")
        if (output.dtype != torch.float32 or output.device != self.device or
                list(output.shape) != fixture["shape"] or not output.is_contiguous() or output.requires_grad):
            raise _NumericalFailure("output dtype/device/shape/layout/inference mismatch")
        storage = output.untyped_storage()
        start, end = storage.data_ptr(), storage.data_ptr() + storage.nbytes()
        for value in (x, scale):
            other = value.untyped_storage()
            if start < other.data_ptr() + other.nbytes() and other.data_ptr() < end:
                independent = False
        self.sync()
        copied = output.cpu()  # No coercion of a failing dtype/layout.
        unchanged = (_tensor_bytes(x.cpu()) == fixture["x"] and
                     _tensor_bytes(scale.cpu()) == fixture["scale"])
        result = check_rmsnorm(cpu_x, cpu_scale, copied)
        check = {"id": check_id, "fixture_id": fixture["id"], "phase": phase, "arm": arm,
                 "input_digest": _fixture_record(fixture)["input_digest"],
                 "output_digest": digest_bytes(_tensor_bytes(copied)), "outcome": result["outcome"],
                 "input_unchanged": unchanged, "independent_storage": independent,
                 "oracle_version": result["oracle_version"], "max_absolute_error": result["max_absolute_error"]}
        # Return the failing record too; the orchestrator saves it before stopping.
        return check

    def events(self):
        torch = self.torch
        return torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)

    def record(self, event):
        event.record(self.stream)

    def elapsed(self, start, stop):
        return start.elapsed_time(stop)

    def memory_start(self):
        torch = self.torch
        starting = (torch.cuda.memory_allocated(self.device), torch.cuda.memory_reserved(self.device))
        torch.cuda.reset_peak_memory_stats(self.device)
        return starting

    def memory_end(self, starting):
        from .cuda_benchmark import memory_peak_delta
        torch = self.torch
        return memory_peak_delta(*starting, torch.cuda.max_memory_allocated(self.device),
                                 torch.cuda.max_memory_reserved(self.device))

    def release(self, output):
        # The caller deletes its sole reference before any subsequent call.
        pass


def _exercise(plan, backend, observation):
    """Fixed lifecycle used by the CUDA child and explicitly tagged fake tests."""
    fixtures = _fixture_bytes(plan["config"]["seed"])
    records = {f["id"]: _fixture_record(f) for f in fixtures}
    if list(records.values()) != plan["fixtures"]:
        raise ValueError("fixture identity drift")
    active = None
    stage = "prepare"
    try:
        backend.prepare(fixtures)
        def checked(output, arm, fixture, phase, identity):
            check = backend.check(output, arm, fixture, phase, identity)
            observation["checks"].append(check)
            if check["outcome"] != "pass" or not check["input_unchanged"] or not check["independent_storage"]:
                raise _NumericalFailure("numerical/storage/input mutation gate failed")
            return check
        stage = "pre_correctness"
        for fixture in fixtures:
            for arm in ARMS:
                output = backend.call(arm, fixture)
                try:
                    backend.sync()
                    checked(output, arm, fixture, "pre", f"pre:{fixture['id']}:{arm}")
                finally:
                    backend.release(output)
                    del output
        for shape in plan["contract"]["timed_shapes"]:
            fixture = next(f for f in fixtures if f["id"].startswith("seeded_") and f["shape"] == shape)
            stage = "warmup"
            for arm in ARMS:
                key = f"{shape[0]}x{shape[1]}:{arm}"
                observation["warmup_completed"][key] = 0
                for iteration in range(plan["contract"]["warmup_per_arm"]):
                    output = backend.call(arm, fixture)
                    try:
                        backend.sync()
                        checked(output, arm, fixture, "warmup", f"warm:{key}:{iteration}")
                    finally:
                        backend.release(output)
                        del output
                    observation["warmup_completed"][key] += 1
            backend.sync()
            for descriptor in _sample_schedule(plan["contract"]):
                if descriptor["shape"] != shape:
                    continue
                active = descriptor
                stage = "timing_events"
                start, stop = backend.events()  # Events created outside the host interval.
                backend.sync()
                starting = backend.memory_start()
                stage = "timing_call"
                host_start = time.perf_counter_ns()
                backend.record(start)
                output = backend.call(descriptor["implementation"], fixture)
                try:
                    backend.record(stop)
                    stage = "timing_completion"
                    backend.sync()
                    host_ns = time.perf_counter_ns() - host_start
                    # Peaks captured before correctness/download/error scratch.
                    memory = backend.memory_end(starting)
                    device_ms = backend.elapsed(start, stop)
                    if (type(device_ms) not in (float, int) or not 0 < device_ms < float("inf") or
                            type(host_ns) is not int or host_ns <= 0):
                        raise _NumericalFailure("invalid/nonpositive event or host sample")
                    stage = "timed_output_correctness"
                    check_id = f"sample:{len(observation['samples'])}"
                    checked(output, descriptor["implementation"], fixture, "sample", check_id)
                    observation["samples"].append({**descriptor, "check_id": check_id,
                        "device_elapsed_ms": device_ms, "component_elapsed_ns": host_ns, "memory": memory,
                        "device_uuid": plan["config"]["device"]["uuid"], "plan_digest": plan["plan_digest"],
                        "input_digest": records[fixture["id"]]["input_digest"], "units": {"device": "ms", "component": "ns"}})
                finally:
                    backend.release(output)
                    del output
                active = None
        stage = "post_correctness"
        # Includes changed-input fixtures, uploaded independently before timing.
        for fixture in fixtures:
            for arm in ARMS:
                output = backend.call(arm, fixture)
                try:
                    backend.sync()
                    checked(output, arm, fixture, "post", f"post:{fixture['id']}:{arm}")
                finally:
                    backend.release(output)
                    del output
        backend.sync()
        observation["lifecycle"]["synchronized_all_work"] = True
        observation["status"] = "measured_advisory" if backend.origin == "real_cuda" else "failed"
        observation["reason"] = "complete trusted CUDA scope" if backend.origin == "real_cuda" else "mock lifecycle; no CUDA measurement"
    except Exception as exc:
        # A RuntimeError from CUDA work may be asynchronous device failure. Keep uncertainty.
        observation["status"] = "failed" if isinstance(exc, (_NumericalFailure, ValueError, NotImplementedError)) else "unknown"
        observation["reason"] = f"{stage}: {type(exc).__name__}"[:4096]
        if active is not None:
            observation["failed_sample"] = {"schedule": active, "stage": stage, "reason": type(exc).__name__}
    return observation


def _child_probe(plan):
    # Rebuild against current bytes/config before touching CUDA.
    plan = _validate_plan(plan)
    observation = _blank_observation(plan, status="unavailable", origin="real_cuda", reason="CUDA unavailable")
    try:
        from .attention import require_torch
        torch = require_torch()
    except RuntimeError:
        return observation
    if not torch.cuda.is_available():
        return observation
    stage = "device_identity"
    try:
        if torch.cuda.device_count() != 1:
            raise ValueError("exactly one visible physical GPU required")
        torch.cuda.set_device(0)
        properties = torch.cuda.get_device_properties(0)
        uuid = getattr(properties, "uuid", None)
        if uuid is not None:
            uuid = str(uuid)
            if not uuid.startswith("GPU-"):
                uuid = "GPU-" + uuid
            uuid = "GPU-" + uuid[4:].lower()
        if uuid != plan["config"]["device"]["uuid"]:
            raise ValueError("observed physical UUID missing or mismatched")
        # Optional installed API; never substitute CUDA-runtime version for driver.
        driver_api = getattr(torch._C, "_cuda_getDriverVersion", None)
        driver = str(driver_api()) if callable(driver_api) else None
        observation["environment"].update(cuda_runtime=torch.version.cuda, driver=driver,
            gpu={"uuid": uuid, "name": properties.name, "compute_capability": [properties.major, properties.minor],
                 "total_bytes": properties.total_memory, "partition": "unverified", "concurrency": "unknown",
                 "mps": "unverified", "reservation_enforcement": "unverified"})
        if not callable(getattr(torch.nn.functional, "rms_norm", None)):
            observation.update(status="failed", reason="unsupported library RMSNorm arm")
            return observation
        observation["lifecycle"]["gpu_may_have_started"] = True
        backend = _CudaBackend(torch, plan, observation)
        stage = "probe"
        return _exercise(plan, backend, observation)
    except ValueError:
        observation.update(status="rejected", reason=f"{stage}: device identity rejected")
    except Exception as exc:
        observation.update(status="unknown", reason=f"{stage}: {type(exc).__name__}")
    return observation


def run_trusted_probe(config, *, execute=False):
    """Build by default; explicit opt-in runs one fixed bounded trusted child."""
    if type(execute) is not bool:
        raise ValueError("execute must be Boolean")
    plan = build_probe_plan(config)
    if not execute:
        return {"plan": plan, "observation": validate_probe_observation(plan, _blank_observation(plan))}
    if any(value and key.startswith(("LD_", "DYLD_")) for key, value in os.environ.items()):
        rejected = _blank_observation(plan, status="rejected", origin="real_cuda",
                                      reason="parent dynamic-loader environment rejected before launcher")
        return {"plan": plan, "observation": validate_probe_observation(plan, rejected)}
    envelope = None
    try:
        # A fixed env launcher excludes credentials/preloads/plugins without global env mutation.
        argv = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "CUDA_DEVICE_ORDER=PCI_BUS_ID",
                f"CUDA_VISIBLE_DEVICES={plan['config']['device']['uuid']}", str(Path(sys.executable).absolute()),
                "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); from compute.rmsnorm_cuda import _child_main; _child_main()",
                str(ROOT)]
        envelope = bounded_process(argv, timeout=plan["config"]["host"]["deadline_seconds"],
                                   max_output=plan["config"]["host"]["max_output_bytes"], stdin=canonical_bytes(plan))
        # Parsing cannot turn incomplete process lifecycle into a successful measurement.
        complete = (type(envelope.get("exit_code")) is int and envelope["exit_code"] == 0 and
                    envelope.get("reason") == "exited" and envelope.get("truncated") is False and
                    envelope.get("process_group_retired") is True)
        if not complete:
            raise _CudaUncertainty("incomplete child/process-group observation")
        observation = strict_json_loads(envelope["output"], cap=plan["config"]["host"]["max_output_bytes"])
        if observation.get("origin") != "real_cuda":
            raise ValueError("child did not report real CUDA origin")
        observation["lifecycle"]["process_group_retired"] = True
        result = validate_probe_observation(plan, observation)
    except Exception as exc:
        # No evidence of when a malformed/interrupted child stopped; conservatively retain possible work.
        result = _blank_observation(plan, status="unknown", origin="real_cuda",
                                    reason=f"parent: {type(exc).__name__}; possible device work")
        result["lifecycle"]["gpu_may_have_started"] = True
        result["lifecycle"]["process_group_retired"] = bool(envelope and envelope.get("process_group_retired") is True)
    return {"plan": plan, "observation": result}


def _child_main():
    plan = strict_json_loads(sys.stdin.buffer.read(1048577))
    result = _child_probe(plan)
    sys.stdout.buffer.write(canonical_bytes(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-trusted-probe", action="store_true")
    args = parser.parse_args()
    with open(args.config, "rb") as stream:
        config = strict_json_loads(stream.read(65537), cap=65536)
    result = run_trusted_probe(validate_probe_config(config), execute=args.run_trusted_probe)
    print(canonical_bytes(result).decode())


if __name__ == "__main__":
    main()
