import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from compute.cache import CacheIdentity, PrefixCache, kv_bytes
from compute.cuda_benchmark import benchmark
from compute.trajectory import Trajectory, group_advantages, masked_objective

try:
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "PyTorch compute extra unavailable")
class AttentionTests(unittest.TestCase):
    def test_cached_decode_hand_oracle_and_wrong_causal_counterexample(self):
        from compute.attention import counterexample

        result = counterexample()
        self.assertEqual(result["scalar"], 6)
        self.assertEqual(result["eager"], 6)
        self.assertEqual(result["explicit_mask_sdpa"], 6)
        self.assertEqual(result["wrong_upper_left_causal"], 2)
        self.assertEqual(result["ledger"]["probabilities"]["values"], [[[[0.25, 0.25, 0.25, 0.25]]]])

    def test_full_prefix_suffix_equivalence_noncontiguous_gqa(self):
        from compute.attention import eager_attention, scalar_attention, sdpa_attention

        generator = torch.Generator().manual_seed(19)
        for cached, appended, hq, hkv in ((0, 3, 2, 2), (3, 1, 4, 1), (2, 3, 4, 2)):
            t = cached + appended
            # Selecting every other D makes actual input layout noncontiguous.
            q = torch.randn(1, hq, t, 6, generator=generator)[..., ::2]
            k = torch.randn(1, hkv, t, 6, generator=generator)[..., ::2]
            v = torch.randn(1, hkv, t, 4, generator=generator)[..., ::2]
            full, _ = eager_attention(q, k, v)
            suffix = q[:, :, cached:, :]
            eager, ledger = eager_attention(suffix, k, v, cached)
            scalar = scalar_attention(suffix, k, v, cached)
            sdpa = sdpa_attention(suffix, k, v, cached)
            torch.testing.assert_close(eager, full[:, :, cached:, :], atol=1e-6, rtol=1e-6)
            torch.testing.assert_close(eager, scalar, atol=1e-6, rtol=1e-6)
            torch.testing.assert_close(eager, sdpa, atol=1e-6, rtol=1e-5)
            self.assertEqual(ledger["head_mapping"], [h // (hq // hkv) for h in range(hq)])
            self.assertFalse(ledger["Q"]["contiguous"])
            self.assertEqual(ledger["K"]["logical_bytes"], 1 * hkv * t * 3 * 4)

    def test_future_perturbation_and_shape_rejection(self):
        from compute.attention import sdpa_attention

        q, k, v = (torch.ones(1, 1, 3, 1) for _ in range(3))
        before = sdpa_attention(q, k, v)
        v[:, :, 2] = 1000
        after = sdpa_attention(q, k, v)
        torch.testing.assert_close(before[:, :, :2], after[:, :, :2])
        self.assertGreater(after[0, 0, 2, 0], 100)
        with self.assertRaises(ValueError):
            sdpa_attention(q, k, v, cached_length=1)

    def test_cuda_skip_is_explicit_and_never_runs_cpu_fallback(self):
        with patch("torch.cuda.is_available", return_value=False):
            result = benchmark()
        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["fallback"])
        self.assertNotIn("results", result)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.identity = CacheIdentity(
            "model-sha", "tokenizer-sha", "template-sha", "none", "tenant-a", "BHTD", "float16"
        )

    def test_ideal_bytes_use_kv_heads_and_rounding(self):
        result = kv_bytes(
            layers=2, batch=1, tokens=4, kv_heads=1, head_dim=2, element_bytes=2, block_tokens=3
        )
        self.assertEqual(result["ideal_bytes"], 64)
        self.assertEqual(result["rounded_block_bytes"], 96)
        self.assertEqual(result["padding_bytes"], 32)

    def test_prefix_parent_identity_partial_tail_and_pinned_pressure(self):
        cache = PrefixCache(block_tokens=2, capacity_blocks=3)
        first = cache.acquire("a", [1, 2, 3, 4, 5], self.identity)
        shared = cache.acquire("b", [1, 2, 3, 4, 9], self.identity)
        self.assertEqual(shared["hits"], 2)
        self.assertEqual(shared["uncached_tail_tokens"], 1)
        changed = cache.acquire("c", [1, 2, 7, 8], self.identity)
        self.assertEqual(changed["hits"], 1)
        self.assertEqual(changed["misses"], 1)
        with self.assertRaises(RuntimeError):
            cache.acquire("d", [1, 2, 3, 4], replace(self.identity, adapter_revision="new-adapter"))
        self.assertNotIn("d", cache.requests)  # Failed acquire leaves no partially pinned owner.
        cache.release("a")
        cache.release("b")
        cache.release("c")
        other_tenant = cache.acquire("d", [1, 2, 3, 4], replace(self.identity, namespace="tenant-b"))
        self.assertEqual(other_tenant["hits"], 0)
        self.assertEqual(other_tenant["misses"], 2)
        cache.release("d")
        # The same second block cannot be reused after a different parent prefix.
        changed_parent = cache.acquire("e", [9, 9, 3, 4], self.identity)
        self.assertNotEqual(first["keys"][1], changed_parent["keys"][1])


class TrajectoryTests(unittest.TestCase):
    def fixture(self):
        return Trajectory(
            (1, 2, 3),
            (1, 2, 3),
            ("action", "observation", "action"),
            (1, 0, 1),
            (math.log(0.5), math.log(0.1), math.log(0.5)),
            (math.log(0.75), math.log(0.9), math.log(0.25)),
            1,
            1,
            "model",
            "tokenizer",
            "environment",
            1.0,
            "protected-grader",
            "completed",
        )

    def test_hand_masked_loss_excludes_observation_and_handles_negative_advantage(self):
        t = self.fixture()
        # Ratios action=[1.5,.5], clipped=[1.2,.8]. Positive min=[1.2,.5] => -.85.
        self.assertAlmostEqual(masked_objective(t, 1)["loss"], -0.85)
        # Negative min=[-1.5,-.8] => +1.15.
        self.assertAlmostEqual(masked_objective(t, -1)["loss"], 1.15)
        self.assertEqual([c["index"] for c in masked_objective(t, 1)["contributions"]], [0, 2])
        t = replace(t, token_kinds=("observation",) * 3, action_mask=(0, 0, 0))
        self.assertEqual(masked_objective(t, 1)["loss"], 0)
        self.assertTrue(masked_objective(t, 1)["zero_action_mask"])

    def test_versions_tokens_mask_and_equal_reward(self):
        t = self.fixture()
        bad = [
            replace(t, training_token_ids=(1, 2, 4)),
            replace(t, action_mask=(1, 1, 1)),
            replace(t, current_policy_version=2),
            replace(t, behavior_logprobs=(-1.0,)),
            replace(t, termination_reason="effect_unknown"),
        ]
        for trajectory in bad:
            with self.subTest(trajectory=trajectory), self.assertRaises(ValueError):
                trajectory.validate()
        self.assertTrue(group_advantages([t, t])["zero_variance"])
        self.assertEqual(group_advantages([t, t])["advantages"], [0.0, 0.0])
        with self.assertRaises(ValueError):
            group_advantages([t, replace(t, behavior_policy_version=0)], max_policy_lag=1)
        replace(t, current_policy_version=2).validate(max_policy_lag=1)
