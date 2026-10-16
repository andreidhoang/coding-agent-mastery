"""Research accounting and configuration regressions from the 2026-10-09 audit."""

import pytest

from evals.analysis import analyze
from evals.fixtures import accepted_fixture, demo_manifest
from evals.manifest import FrozenManifest
from evals.simulation import Arrival, replay_serving


@pytest.mark.parametrize("counter,before", [("settled_usd", 7), ("input_tokens", 100), ("cpu_seconds", 3)])
def test_consumed_resources_cannot_disappear_in_result_revision(counter, before):
    manifest = demo_manifest(tasks_count=1, trials=1, arms=("bare", "coordinated_n2"))
    row = manifest.read()["planned_rows"][0]
    initial = accepted_fixture(row, result_id="v1", recorded_at=100, **{counter: before})
    revised = accepted_fixture(row, result_id="v2", supersedes_id="v1", recorded_at=110, **{counter: 0})
    with pytest.raises(ValueError):
        analyze(manifest, [initial, revised], bootstrap=10)


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), True])
def test_serving_rates_must_represent_finite_positive_work(rate):
    with pytest.raises((ValueError, TypeError)):
        replay_serving([Arrival("one", 0, 1, 1)], n=1, prefill_tokens_per_second=rate)


def test_boolean_is_not_a_frozen_trial_count():
    data = demo_manifest(tasks_count=1, trials=1).read()
    data["trials"] = True
    with pytest.raises((ValueError, TypeError)):
        FrozenManifest.freeze(data)


def test_finite_serving_rate_must_not_overflow_computed_time():
    with pytest.raises((ValueError, TypeError)):
        replay_serving([Arrival("one", 0, 1, 1)], n=1, prefill_tokens_per_second=1e-320)


def test_settled_allocation_spend_cannot_be_reclaimed_by_observation():
    from evals.allocation import Allocation

    allocation = Allocation.static(
        10, 2, {"coordinator": 0, "integration": 0, "verification": 0, "cleanup": 0}
    )
    allocation.observe_exposure("worker_0", settled=5, reserved=0, unknown=0)
    with pytest.raises(ValueError):
        allocation.observe_exposure("worker_0", settled=0, reserved=0, unknown=0)


def test_tool_return_after_prefix_eviction_prefills_missing_history():
    # Zero generated tokens isolates prefix eviction from output-history policy.
    replay = replay_serving(
        [
            Arrival("a", 0, 10, 0, tool_gap_seconds=10, appended_tokens=1, prefix_identity="A"),
            Arrival("b", 2, 10, 0, prefix_identity="B"),
        ],
        n=2,
        cache_capacity_tokens=10,
        prefill_tokens_per_second=10,
    )
    assert any(e["event"] == "cache_evict" and e["prefix_identity"] == "A" for e in replay["trace"])
    appended = replay["records"]["a"]["model_stages"][1]
    assert not appended["warm"]
    assert appended["prefill_tokens"] == 11


def test_cache_observation_mutation_cannot_change_owned_blocks():
    from compute.cache import CacheIdentity, PrefixCache

    cache = PrefixCache(block_tokens=1, capacity_blocks=1)
    identity = CacheIdentity("m", "t", "template", "none", "tenant", "BHTD", "float32")
    observation = cache.acquire("a", [1], identity)
    observation["keys"].clear()
    cache.release("a")
    assert all(not block.owners for block in cache.blocks.values())
    # A new unrelated block must be able to replace the released block.
    assert cache.acquire("b", [2], identity)["misses"] == 1


def test_primary_contrast_requires_distinct_arms():
    data = demo_manifest(tasks_count=1, trials=1).read()
    data["primary_contrast"] = ["bare", "bare"]
    with pytest.raises(ValueError):
        FrozenManifest.freeze(data)


@pytest.mark.parametrize("field", ["output_tokens", "human_review_minutes"])
def test_all_consumed_resource_categories_are_cumulative(field):
    frozen = demo_manifest(tasks_count=1, trials=1, arms=("bare", "coordinated_n2"))
    row = frozen.read()["planned_rows"][0]
    initial = accepted_fixture(row, result_id="first", recorded_at=100, **{field: 2})
    revised = accepted_fixture(row, result_id="second", supersedes_id="first", recorded_at=110, **{field: 1})
    with pytest.raises(ValueError, match="cumulative"):
        analyze(frozen, [initial, revised], bootstrap=10)


def test_reconciliation_can_lower_outstanding_exposure_without_erasing_consumption():
    frozen = demo_manifest(tasks_count=1, trials=1, arms=("bare", "coordinated_n2"))
    row = frozen.read()["planned_rows"][0]
    initial = {
        "row_id": row["row_id"],
        "result_id": "first",
        "recorded_at": 100,
        "status": "effect_unknown",
        "settled_usd": 2,
        "unknown_usd": 7,
        "reserved_usd": 2,
        "input_tokens": 100,
        "cpu_seconds": 3,
    }
    revised = {
        **initial,
        "result_id": "second",
        "supersedes_id": "first",
        "recorded_at": 110,
        "status": "candidate_failed",
        "settled_usd": 5,
        "unknown_usd": 0,
        "reserved_usd": 0,
    }
    report = analyze(frozen, [initial, revised], bootstrap=10)
    assert report["accounting"]["settled_usd"] == 5
    assert report["accounting"]["total_exposure_usd"] == 5
    assert report["accounting"]["input_tokens"] == 100
    assert report["accounting"]["cpu_seconds"] == 3


@pytest.mark.parametrize("capacity", [0, 10])
def test_tool_return_rebuilds_output_history_and_only_hits_resident_initial_prefix(capacity):
    report = replay_serving(
        [Arrival("a", 0, 10, 3, tool_gap_seconds=2, appended_tokens=2, prefix_identity="A")],
        n=1,
        cache_capacity_tokens=capacity,
        prefill_tokens_per_second=10,
    )
    second = report["records"]["a"]["model_stages"][1]
    assert second["full_prompt_tokens"] == 15
    assert second["cache_hit_tokens"] == (10 if capacity else 0)
    assert second["prefill_tokens"] == (5 if capacity else 15)
    assert second["warm"] is bool(capacity)


def test_cache_return_and_trace_do_not_alias_owned_key_sequence():
    from compute.cache import CacheIdentity, PrefixCache

    identity = CacheIdentity("m", "t", "template", "none", "tenant", "BHTD", "float32")
    cache = PrefixCache(block_tokens=1, capacity_blocks=1)
    record = cache.acquire("a", [1], identity)
    original_key = record["keys"][0]
    record["keys"].clear()
    record["evictions"].append("fabricated")
    assert cache.trace[0]["keys"] == [original_key]
    assert not cache.trace[0]["evictions"]
    cache.release("a")
    assert not cache.blocks[original_key].owners


@pytest.mark.parametrize(
    "module,field,value",
    [
        ("serving", "n", True),
        ("serving", "model_capacity", 1.5),
        ("serving", "queue_limit", False),
        ("serving", "cache_capacity_tokens", True),
        ("serving", "decode_tokens_per_second", float("inf")),
        ("dag", "n", True),
        ("dag", "cpu_capacity", 1.5),
        ("dag", "model_capacity", True),
        ("benchmark", "batch", True),
        ("benchmark", "dim", 1.5),
        ("benchmark", "cached", True),
        ("benchmark", "warmup", float("nan")),
        ("benchmark", "repeats", True),
        ("benchmark", "seed", True),
    ],
)
def test_discrete_resource_seams_reject_boolean_fractional_and_nonfinite_contracts(module, field, value):
    from compute.cuda_benchmark import benchmark
    from evals.simulation import Node, simulate_dag

    kwargs = {field: value}
    with pytest.raises(ValueError):
        if module == "serving":
            replay_serving([Arrival("a", 0, 1, 1)], **({"n": 1} | kwargs))
        elif module == "dag":
            simulate_dag([Node("a", 1)], **({"n": 1} | kwargs))
        else:
            benchmark(**kwargs)  # Contract checks precede CUDA availability.


@pytest.mark.parametrize("kwargs", [{"block_tokens": True}, {"capacity_blocks": True}])
def test_prefix_block_counts_are_not_booleans(kwargs):
    from compute.cache import PrefixCache

    with pytest.raises(ValueError):
        PrefixCache(**({"block_tokens": 1, "capacity_blocks": 1} | kwargs))


def test_kv_value_dimension_and_token_identity_are_not_booleans():
    from compute.cache import CacheIdentity, PrefixCache, kv_bytes

    with pytest.raises(ValueError):
        kv_bytes(layers=1, batch=1, tokens=1, kv_heads=1, head_dim=1, element_bytes=2, value_head_dim=True)
    identity = CacheIdentity("m", "t", "template", "none", "tenant", "BHTD", "float32")
    with pytest.raises(ValueError):
        PrefixCache(block_tokens=1, capacity_blocks=1).acquire("a", [True], identity)


@pytest.mark.parametrize("field,value", [("trials", True), ("assignment_seed", True)])
def test_manifest_count_and_seed_contracts(field, value):
    data = demo_manifest(tasks_count=1, trials=1).read()
    data[field] = value
    with pytest.raises(ValueError):
        FrozenManifest.freeze(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("decision_time", True),
        ("decision_time", float("nan")),
        ("observed_at", True),
        ("estimated_remaining_usd", True),
    ],
)
def test_allocation_observations_require_finite_nonboolean_numbers(field, value):
    from evals.allocation import Allocation

    allocation = Allocation.static(
        10, 1, {"coordinator": 0, "integration": 0, "verification": 0, "cleanup": 0}
    )
    observation = {
        "worker_id": "worker_0",
        "observation_id": "obs",
        "observed_at": 1,
        "state": "running",
        "estimated_remaining_usd": 1,
    }
    decision_time = 1
    if field == "decision_time":
        decision_time = value
    else:
        observation[field] = value
    with pytest.raises(ValueError):
        allocation.progress_aware([observation], decision_time)
    assert allocation.workers["worker_0"].allowance == 10  # Failure is before redistribution.


def test_dag_rejects_overflow_in_derived_path():
    from evals.simulation import Node, simulate_dag

    with pytest.raises(ValueError):
        simulate_dag([Node("a", 1e308), Node("b", 1e308, ("a",))], n=1)


def test_memory_peak_deltas_identify_starting_live_and_cached_residency():
    from compute.cuda_benchmark import memory_peak_delta

    result = memory_peak_delta(100, 400, 180, 400)
    assert result["starting_allocated_bytes"] == 100
    assert result["starting_reserved_bytes"] == 400
    assert result["incremental_peak_allocated_bytes"] == 80
    assert result["incremental_peak_reserved_bytes"] == 0
    with pytest.raises(ValueError):
        memory_peak_delta(100, 400, 80, 400)
    with pytest.raises(ValueError):
        memory_peak_delta(True, 400, 180, 400)


@pytest.mark.parametrize(
    "field,value",
    [
        ("behavior_policy_version", True),
        ("reward", True),
        ("action_mask", (True,)),
        ("sampled_token_ids", (True,)),
        ("training_token_ids", (1.0,)),
        ("behavior_logprobs", (True,)),
    ],
)
def test_trajectory_numbers_reject_boolean_or_fractional_identity(field, value):
    from dataclasses import replace
    from compute.trajectory import Trajectory

    trajectory = Trajectory(
        (1,),
        (1,),
        ("action",),
        (1,),
        (-1.0,),
        (-1.0,),
        1,
        1,
        "model",
        "tokens",
        "environment",
        1.0,
        "fixture",
        "completed",
    )
    with pytest.raises(ValueError):
        replace(trajectory, **{field: value}).validate()


def test_absolute_cached_position_does_not_accept_boolean_length():
    torch = pytest.importorskip("torch")
    from compute.attention import absolute_mask, sdpa_attention

    with pytest.raises(ValueError):
        absolute_mask(1, 2, True)
    with pytest.raises(ValueError):
        sdpa_attention(torch.zeros(1, 1, 1, 1), torch.zeros(1, 1, 2, 1), torch.zeros(1, 1, 2, 1), True)
