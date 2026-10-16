"""CPU/fake contract tests only: no physical CUDA, timing, isolation or retirement proof."""

import copy
import json
import math
import struct
from unittest.mock import patch

import pytest

from compute import gpu_contract as gc
from compute import rmsnorm_cuda as probe


UUID = "GPU-01234567-89ab-cdef-0123-456789abcdef"


def config():
    return {"schema": gc.SCHEMA, "mode": "trusted_authored", "paid_execution": False,
            "device": {"uuid": UUID, "partition": "whole_gpu", "sharing": "exclusive_operator_declared",
                       "reservation": "whole_device_capacity"},
            "host": {"deadline_seconds": 120, "max_output_bytes": 1048576}, "seed": 7}


@pytest.fixture(scope="module")
def plan():
    return gc.build_probe_plan(config())


class FakeBackend:
    """A lifecycle ledger with fabricated samples; never a CUDA evidence producer."""
    origin = "mock"

    def __init__(self, observation, defect=None):
        self.observation, self.defect = observation, defect
        self.live = False
        self.ledger = []
        self.synced = False
        self.calls = 0

    def prepare(self, fixtures):
        self.ledger.append(("prepare", len(fixtures)))
        self.observation["lifecycle"]["gpu_may_have_started"] = True

    def call(self, arm, fixture):
        assert not self.live, "previous output retained across next call"
        self.live, self.synced = True, False
        self.calls += 1
        self.ledger.append(("call", arm, fixture["id"]))
        return {"arm": arm}

    def sync(self):
        self.synced = True
        self.ledger.append(("sync",))
        if self.defect == "sync_fault" and self.calls >= 41:
            raise probe._CudaUncertainty("fake asynchronous failure")

    def check(self, output, arm, fixture, phase, check_id):
        assert self.synced
        self.ledger.append(("check", phase, arm, fixture["id"]))
        check = {"id": check_id, "fixture_id": fixture["id"], "phase": phase, "arm": arm,
                 "input_digest": gc._fixture_record(fixture)["input_digest"], "output_digest": "0" * 64,
                 "outcome": "pass", "input_unchanged": True, "independent_storage": True,
                 "oracle_version": "python-float64-fsum-v1", "max_absolute_error": 0.0}
        if self.defect == "gpu_mutation" and phase == "pre":
            check["input_unchanged"] = False  # CPU fixture bytes have stayed unchanged.
        if self.defect == "timed_wrong" and phase == "sample":
            check["outcome"] = "fail"
        if self.defect == "post_wrong" and phase == "post":
            check["outcome"] = "fail"
        return check

    def release(self, output):
        assert self.live
        self.live = False
        self.ledger.append(("release",))

    def events(self):
        self.ledger.append(("events",))
        return "start", "stop"

    def record(self, event):
        self.ledger.append(("record", event))
        self.synced = False

    def elapsed(self, start, stop):
        assert self.synced, "elapsed read before synchronization"
        self.ledger.append(("elapsed",))
        return 0 if self.defect == "enqueue_only" else 1.0

    def memory_start(self):
        self.ledger.append(("memory_start",))
        return (16, 32)

    def memory_end(self, starting):
        assert self.synced
        self.ledger.append(("memory_end",))
        return {"starting_allocated_bytes": 16, "starting_reserved_bytes": 32,
                "peak_allocated_bytes": 24, "peak_reserved_bytes": 32,
                "incremental_peak_allocated_bytes": 8, "incremental_peak_reserved_bytes": 0}


def fake_run(plan, defect=None):
    observation = gc._blank_observation(plan, origin="mock", status="failed", reason="fake lifecycle")
    backend = FakeBackend(observation, defect)
    with patch.object(probe.time, "perf_counter_ns", side_effect=range(1, 10000)):
        result = probe._exercise(plan, backend, observation)
    return result, backend


def declared_real_fixture(plan):
    """Fabricated real-shaped JSON for reducer tests; never run through a real child."""
    observation, _ = fake_run(plan)
    observation["origin"] = "real_cuda"
    observation["status"] = "measured_advisory"
    observation["lifecycle"]["process_group_retired"] = True
    observation["environment"].update(cuda_runtime="fake-test-only", driver="fake-test-only", gpu={
        "uuid": UUID, "name": "FAKE TEST ONLY", "compute_capability": [8, 0], "total_bytes": 1024,
        "partition": "whole_gpu_observed", "concurrency": "no_known_contention_observed", "mps": "absent_observed",
        "reservation_enforcement": "unverified"})
    return observation


def test_default_is_cpu_plan_without_torch_import_or_external_action(plan):
    with patch.object(probe, "bounded_process", side_effect=AssertionError("child launched")), \
            patch.object(probe, "_child_probe", side_effect=AssertionError("CUDA touched")), \
            patch("socket.socket", side_effect=AssertionError("network touched")), \
            patch("subprocess.Popen", side_effect=AssertionError("subprocess touched")):
        result = probe.run_trusted_probe(config())
    assert result["plan"] == plan
    assert result["observation"]["status"] == "not_run"
    assert result["observation"]["samples"] == []
    assert result["observation"]["fallback"] is None


@pytest.mark.parametrize("field,value", [("schema", "v2"), ("mode", "candidate"), ("paid_execution", True),
                                           ("paid_execution", 0), ("seed", True), ("seed", -1),
                                           ("seed", 2147483648), ("seed", math.nan)])
def test_manifest_scalar_rejections(field, value):
    candidate = config()
    candidate[field] = value
    with pytest.raises(ValueError):
        gc.validate_probe_config(candidate)


@pytest.mark.parametrize("field,value", [("uuid", "0"), ("uuid", [UUID]), ("uuid", "MIG-" + UUID),
                                          ("partition", "mig"), ("sharing", "mps"),
                                          ("reservation", "hard_vram_limit")])
def test_device_contract_rejections(field, value):
    candidate = config()
    candidate["device"][field] = value
    with pytest.raises(ValueError):
        gc.validate_probe_config(candidate)


@pytest.mark.parametrize("field,value", [("deadline_seconds", True), ("deadline_seconds", 0),
                                          ("deadline_seconds", 601), ("max_output_bytes", False),
                                          ("max_output_bytes", 1023), ("max_output_bytes", 1048577)])
def test_host_bounds(field, value):
    candidate = config()
    candidate["host"][field] = value
    with pytest.raises(ValueError):
        gc.validate_probe_config(candidate)


@pytest.mark.parametrize("key", ["candidate", "command", "source", "module", "hard_vram_limit_bytes", "timing"])
def test_unknown_executable_or_quota_fields_rejected(key):
    candidate = config()
    candidate[key] = "not executable"
    with pytest.raises(ValueError):
        gc.validate_probe_config(candidate)


def test_detached_contract_plan_and_config(plan):
    cfg = config()
    owned = gc.validate_probe_config(cfg)
    owned["device"]["uuid"] = "changed"
    assert cfg["device"]["uuid"] == UUID
    contract = gc.probe_contract()
    contract["timed_shapes"][0][0] = 99
    assert gc.probe_contract()["timed_shapes"][0] == [1, 33]
    observation = gc.validate_probe_observation(plan, gc._blank_observation(plan))
    observation["source_hashes"].clear()
    assert plan["source_hashes"]


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                                b'{} garbage', b'\xff', b'[' * 30 + b']' * 30])
def test_strict_json(raw):
    with pytest.raises(ValueError):
        gc.strict_json_loads(raw)


def test_source_fixture_seed_and_policy_identity(plan):
    changed = copy.deepcopy(plan)
    changed["source_hashes"]["compute/rmsnorm.py"] = "0" * 64
    with pytest.raises(ValueError):
        gc.validate_probe_observation(changed, gc._blank_observation(changed))
    changed = config()
    changed["seed"] += 1
    second = gc.build_probe_plan(changed)
    assert plan["plan_digest"] != second["plan_digest"]
    assert plan["fixtures"][-2]["input_digest"] != second["fixtures"][-2]["input_digest"]


def test_fixture_tiny_trace_independent_hand_math():
    fixtures = gc._fixture_bytes(7)
    tiny = fixtures[0]
    assert struct.unpack("<3f", tiny["x"]) == (1, 2, 2)
    assert struct.unpack("<3f", tiny["scale"]) == (2, -3, 0)
    expected = [2 / math.sqrt(3.00001), -6 / math.sqrt(3.00001), 0]
    torch = pytest.importorskip("torch")
    x = torch.tensor([[1., 2., 2.]], dtype=torch.float32)
    scale = torch.tensor([2., -3., 0.], dtype=torch.float32)
    output = probe._eager_arm(torch, x, scale)
    assert output.tolist()[0] == pytest.approx(expected, abs=1e-5, rel=1e-4)
    from compute.rmsnorm import check_rmsnorm
    assert check_rmsnorm(x, scale, output)["outcome"] == "pass"
    for wrong in (x / math.sqrt(3.00001), x / math.sqrt(9.00001) * scale,
                  x / (math.sqrt(3) + 1e-5) * scale + 1):
        assert check_rmsnorm(x, scale, wrong)["outcome"] == "fail"


def test_fake_lifecycle_preserves_exact_sequence_and_never_real_verdict(plan):
    observation, backend = fake_run(plan)
    assert observation["origin"] == "mock" and observation["status"] == "failed"
    assert len(observation["samples"]) == 160
    assert not backend.live
    assert len([i for i in backend.ledger if i[0] == "release"]) == backend.calls
    first_events = next(i for i, value in enumerate(backend.ledger) if value[0] == "events")
    before = backend.ledger[:first_events]
    assert len([i for i in before if i[:2] == ("check", "pre")]) == 20
    assert len([i for i in before if i[:2] == ("check", "warmup")]) == 20
    first = backend.ledger[first_events:first_events + 11]
    assert [entry[0] for entry in first] == ["events", "sync", "memory_start", "record", "call", "record",
                                           "sync", "memory_end", "elapsed", "check", "release"]
    result = gc.validate_probe_observation(plan, observation)
    assert result["ratios"] == {} and result["summaries"] == {}
    observation["status"] = "measured_advisory"
    with pytest.raises(ValueError, match="mock"):
        gc.validate_probe_observation(plan, observation)


@pytest.mark.parametrize("defect,status", [("gpu_mutation", "failed"), ("timed_wrong", "failed"),
                                            ("post_wrong", "failed"), ("enqueue_only", "failed"),
                                            ("sync_fault", "unknown")])
def test_fake_failure_controls_remove_performance(plan, defect, status):
    observation, backend = fake_run(plan, defect)
    assert observation["status"] == status
    assert not backend.live
    validated = gc.validate_probe_observation(plan, observation)
    assert validated["ratios"] == {} and validated["summaries"] == {}
    if defect in {"timed_wrong", "enqueue_only", "sync_fault"}:
        assert observation["failed_sample"] is not None


def test_independent_summary_medians_and_withholding(plan):
    observation = declared_real_fixture(plan)
    for index, sample in enumerate(observation["samples"]):
        sample["device_elapsed_ms"] = 2 if sample["implementation"] == "eager" else 1
        sample["component_elapsed_ns"] = 200 if sample["implementation"] == "eager" else 100
    observation["summaries"] = {"forged": 999}
    observation["ratios"] = {"forged": 999}
    result = gc.validate_probe_observation(plan, observation)
    assert result["summaries"]["1x33"]["eager"]["device_elapsed_ms"] == {
        "count": 30, "median": 2.0, "minimum": 2, "maximum": 2, "spread": 0}
    assert result["ratios"]["1x33"]["device"] == 2
    for sample in observation["samples"]:
        if sample["arm"] == "eager_a":
            sample["device_elapsed_ms"] = 3
    assert gc.validate_probe_observation(plan, observation)["ratios"]["1x33"]["status"] == "unstable_measurement"
    assert gc.validate_probe_observation(plan, observation)["ratios"]["1x33"]["device"] is None
    observation = declared_real_fixture(plan)
    observation["environment"]["driver"] = None
    assert gc.validate_probe_observation(plan, observation)["ratios"]["1x33"]["device"] is None


@pytest.mark.parametrize("mutation", ["nan", "zero", "host_bool", "units", "order", "count", "memory", "uuid", "plan", "shape_bool"])
def test_sample_semantic_defects(plan, mutation):
    observation = declared_real_fixture(plan)
    sample = observation["samples"][0]
    if mutation == "nan":
        sample["device_elapsed_ms"] = math.nan
    elif mutation == "zero":
        sample["device_elapsed_ms"] = 0
    elif mutation == "host_bool":
        sample["component_elapsed_ns"] = True
    elif mutation == "units":
        sample["units"]["device"] = "ns"
    elif mutation == "order":
        sample["pair_index"] = 1
    elif mutation == "count":
        observation["samples"].pop()
    elif mutation == "memory":
        sample["memory"]["incremental_peak_allocated_bytes"] = -1
    elif mutation == "uuid":
        sample["device_uuid"] = "GPU-other"
    elif mutation == "plan":
        sample["plan_digest"] = "0" * 64
    elif mutation == "shape_bool":
        sample["shape"][0] = True
    with pytest.raises(ValueError):
        gc.validate_probe_observation(plan, observation)


@pytest.mark.parametrize("field,value", [("reason", "timeout"), ("exit_code", 1), ("exit_code", True),
                                         ("truncated", True), ("process_group_retired", False)])
def test_plausible_success_plus_incomplete_exit_never_measured(plan, field, value):
    observation = declared_real_fixture(plan)
    envelope = {"reason": "exited", "exit_code": 0, "truncated": False, "process_group_retired": True,
                "output": json.dumps(observation).encode()}
    envelope[field] = value
    with patch.object(probe, "bounded_process", return_value=envelope) as process:
        result = probe.run_trusted_probe(config(), execute=True)
    assert process.call_count == 1
    assert result["observation"]["status"] == "unknown"
    assert result["observation"]["lifecycle"]["gpu_may_have_started"] is True
    assert result["observation"]["lifecycle"]["external_device_retirement"] == "unverified"
    assert result["observation"]["ratios"] == {}


def test_fixed_child_argv_excludes_credentials_and_hooks(plan):
    unavailable = gc._blank_observation(plan, status="unavailable", origin="real_cuda", reason="fake absent CUDA")
    envelope = {"reason": "exited", "exit_code": 0, "truncated": False, "process_group_retired": True,
                "output": json.dumps(unavailable).encode()}
    with patch.object(probe, "bounded_process", return_value=envelope) as process:
        result = probe.run_trusted_probe(config(), execute=True)
    assert result["observation"]["status"] == "unavailable"
    argv = process.call_args.args[0]
    assert argv[:3] == ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin"]
    assert [arg for arg in argv if "=" in arg] == ["PATH=/usr/bin:/bin", "CUDA_DEVICE_ORDER=PCI_BUS_ID",
                                                  f"CUDA_VISIBLE_DEVICES={UUID}"]
    assert "HOME=" not in " ".join(argv) and "CODEX_HOME=" not in " ".join(argv)
    assert process.call_args.kwargs["stdin"] == gc.canonical_bytes(plan)


def test_explicit_child_missing_cuda_mock_no_fallback(plan):
    class FakeCuda:
        def is_available(self):
            return False
    class FakeTorch:
        cuda = FakeCuda()
    with patch("compute.attention.require_torch", return_value=FakeTorch()):
        observation = probe._child_probe(plan)
    assert observation["status"] == "unavailable"
    assert observation["samples"] == [] and observation["fallback"] is None


@pytest.mark.parametrize("raw", [b'', b'{}', b'{"status":"a","status":"b"}', b'{}x'])
def test_malformed_or_missing_child_result_is_unknown(plan, raw):
    envelope = {"reason": "exited", "exit_code": 0, "truncated": False, "process_group_retired": True, "output": raw}
    with patch.object(probe, "bounded_process", return_value=envelope):
        assert probe.run_trusted_probe(config(), execute=True)["observation"]["status"] == "unknown"


def test_no_physical_authority_and_no_failed_check_can_be_promoted(plan):
    observation = declared_real_fixture(plan)
    observation["lifecycle"]["external_device_retirement"] = "retired"
    with pytest.raises(ValueError):
        gc.validate_probe_observation(plan, observation)
    observation = declared_real_fixture(plan)
    observation["checks"][0]["input_unchanged"] = False
    with pytest.raises(ValueError):
        gc.validate_probe_observation(plan, observation)


def test_actual_check_path_detects_simulated_gpu_mutation_with_cpu_original_unchanged(plan):
    """CPU stand-in exercises CUDA check mechanics; it is not a GPU result."""
    torch = pytest.importorskip("torch")
    fixture = gc._fixture_bytes(config()["seed"])[0]
    x = torch.tensor([[1., 2., 2.]], dtype=torch.float32)
    scale = torch.tensor([2., -3., 0.], dtype=torch.float32)
    gpu_x, gpu_scale = x.clone(), scale.clone()  # Simulated CUDA copies on CPU.
    backend = object.__new__(probe._CudaBackend)
    backend.torch, backend.device = torch, torch.device("cpu")
    backend.cpu = {fixture["id"]: (x, scale)}
    backend.inputs = {fixture["id"]: (gpu_x, gpu_scale)}
    backend.sync = lambda: None
    output = probe._eager_arm(torch, gpu_x, gpu_scale)
    good = backend.check(output, "eager", fixture, "pre", "cpu-standin-good")
    assert good["outcome"] == "pass" and good["input_unchanged"]
    gpu_x[0, 0] = 99
    changed = backend.check(output, "eager", fixture, "pre", "cpu-standin-mutation")
    assert changed["outcome"] == "pass" and changed["input_unchanged"] is False
    assert x.tolist() == [[1., 2., 2.]]  # CPU originals alone do not establish GPU immutability.
    gpu_x.copy_(x)
    alias = backend.check(gpu_x, "eager", fixture, "pre", "cpu-standin-alias")
    assert alias["independent_storage"] is False
    for invalid in (output.double(), output.t(), torch.full_like(output, math.nan)):
        if invalid.dtype != torch.float32 or list(invalid.shape) != fixture["shape"]:
            with pytest.raises(probe._NumericalFailure):
                backend.check(invalid, "eager", fixture, "pre", "cpu-standin-invalid")
        else:
            assert backend.check(invalid, "eager", fixture, "pre", "cpu-standin-invalid")["outcome"] == "invalid"


def test_tiny_magnitude_epsilon_defect_independently_rejected():
    torch = pytest.importorskip("torch")
    from compute.rmsnorm import check_rmsnorm
    x = torch.tensor([[1e-4, 2e-4, 2e-4]], dtype=torch.float32)
    scale = torch.tensor([2., -3., .5], dtype=torch.float32)
    exact_x = x.tolist()[0]
    expected = [value * weight / math.sqrt(sum(v*v for v in exact_x)/3 + 1e-5)
                for value, weight in zip(exact_x, scale.tolist())]
    output = probe._eager_arm(torch, x, scale)
    assert output.tolist()[0] == pytest.approx(expected, abs=1e-5, rel=1e-4)
    wrong = x / (torch.sqrt((x*x).mean(dim=1, keepdim=True)) + 1e-5) * scale
    assert check_rmsnorm(x, scale, wrong)["outcome"] == "fail"


def test_plan_schedule_lists_are_detached(plan):
    schedule = list(gc._sample_schedule(plan["contract"]))
    schedule[0]["shape"][0] = 44
    schedule[0]["order"].clear()
    assert plan["contract"]["timed_shapes"][0] == [1, 33]
    assert schedule[2]["order"] == ["pytorch_rms_norm", "eager"]


def test_parent_loader_hook_rejected_before_env_launcher():
    with patch.dict("os.environ", {"LD_PRELOAD": "/fake/not-executed.so"}), \
            patch.object(probe, "bounded_process", side_effect=AssertionError("launcher must not execute")):
        result = probe.run_trusted_probe(config(), execute=True)
    assert result["observation"]["status"] == "rejected"
    assert result["observation"]["lifecycle"]["gpu_may_have_started"] is False


@pytest.mark.parametrize("field,value", [("cpu_threads", True), ("warmup_per_arm", 10.0),
                                        ("fixture_shape", True), ("fixture_bytes", 12.0)])
@pytest.mark.parametrize("recompute_digest", [False, True])
def test_plan_identity_rejects_equal_python_values_with_changed_json_types(plan, field, value, recompute_digest):
    candidate = copy.deepcopy(plan)
    if field == "fixture_shape":
        candidate["fixtures"][0]["shape"][0] = value
    elif field == "fixture_bytes":
        candidate["fixtures"][0]["x_bytes"] = value
    else:
        candidate["contract"][field] = value
    assert candidate == plan  # Python equality is weaker than byte identity.
    if recompute_digest:
        candidate["plan_digest"] = gc.digest_json({k: v for k, v in candidate.items() if k != "plan_digest"})
    with pytest.raises(ValueError, match="identity mismatch"):
        gc.validate_probe_observation(candidate, gc._blank_observation(candidate))
    with patch("compute.attention.require_torch", side_effect=AssertionError("child must reject before CUDA")):
        with pytest.raises(ValueError, match="identity mismatch"):
            probe._child_probe(candidate)


def test_complete_measurement_rejects_contradictory_failed_sample(plan):
    observation = declared_real_fixture(plan)
    observation["failed_sample"] = {"schedule": None, "stage": "timing_completion",
                                    "reason": "fabricated CUDA synchronization failed"}
    with pytest.raises(ValueError, match="complete measurement"):
        gc.validate_probe_observation(plan, observation)


@pytest.mark.parametrize("outcome", ["pass", "fail"])
def test_numerical_pass_and_fail_require_nonnull_error_metric(plan, outcome):
    observation, _ = fake_run(plan)
    observation["checks"][0].update(outcome=outcome, max_absolute_error=None)
    with pytest.raises(ValueError, match="finite error metric"):
        gc.validate_probe_observation(plan, observation)


def test_complete_measurement_rejects_null_passing_error_metric(plan):
    observation = declared_real_fixture(plan)
    observation["checks"][0]["max_absolute_error"] = None
    with pytest.raises(ValueError, match="finite error metric"):
        gc.validate_probe_observation(plan, observation)


def test_explicit_invalid_output_can_retain_null_error_metric(plan):
    observation, _ = fake_run(plan)
    observation["checks"][0].update(outcome="invalid", max_absolute_error=None)
    result = gc.validate_probe_observation(plan, observation)
    assert result["checks"][0]["max_absolute_error"] is None
    assert result["status"] == "failed" and result["ratios"] == {}
