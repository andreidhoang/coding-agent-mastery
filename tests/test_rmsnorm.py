"""NV-S0 CPU semantics, independent oracle and advisory observation boundaries."""

import copy
import json
import math
import unittest
import warnings

try:
    import torch
except ImportError:
    torch = None


def hand_oracle(x, scale):
    """Use scalar exact FP32 values, without any production RMSNorm helper."""
    values = []
    weights = scale.tolist()
    for row in x.tolist():
        denominator = math.sqrt(math.fsum(value * value for value in row) / len(row) + 1e-5)
        values.append([value / denominator * weight for value, weight in zip(row, weights)])
    return torch.tensor(values, dtype=torch.float64)


@unittest.skipIf(torch is None, "PyTorch compute extra unavailable")
class RMSNormTests(unittest.TestCase):
    def setUp(self):
        from compute.rmsnorm import check_rmsnorm, rmsnorm_eager, rmsnorm_reference

        self.reference = rmsnorm_reference
        self.eager = rmsnorm_eager
        self.check = check_rmsnorm

    def assert_observation(self, observation, outcome):
        self.assertEqual(observation["outcome"], outcome)
        self.assertIn("reason", observation)
        for key in ("input_digest", "contract_digest"):
            self.assertIsInstance(observation[key], str)
            self.assertTrue(observation[key])
        self.assertIn("output_digest", observation)
        # A round trip also rejects tensors, NaN/Infinity and other non-JSON evidence.
        self.assertEqual(json.loads(json.dumps(observation, allow_nan=False)), observation)
        for unsupported_claim in ("speedup", "gpu_measurement", "accepted_task", "task_accepted"):
            self.assertNotIn(unsupported_claim, observation)

    def assert_numerically_correct(self, x, scale):
        expected = hand_oracle(x, scale)
        reference = self.reference(x, scale)
        eager = self.eager(x, scale)
        self.assertEqual(reference.dtype, torch.float64)
        self.assertEqual(eager.dtype, torch.float32)
        for result in (reference, eager):
            self.assertEqual(result.device.type, "cpu")
            self.assertEqual(tuple(result.shape), tuple(x.shape))
            self.assertTrue(result.is_contiguous())
        torch.testing.assert_close(reference, expected, atol=1e-14, rtol=1e-14)
        errors = (eager.to(torch.float64) - expected).abs()
        self.assertTrue(bool((errors <= 1e-5 + 1e-4 * expected.abs()).all()))
        observation = self.check(x, scale, eager)
        self.assert_observation(observation, "pass")
        self.assertEqual(observation["failing_elements"], 0)
        self.assertAlmostEqual(observation["max_absolute_error"], errors.max().item(), places=14)
        return reference, eager

    def test_hand_calculation_and_nonunit_negative_zero_scale(self):
        x = torch.tensor([[1.0, 2.0, 2.0]])
        scale = torch.ones(3)
        reference, _ = self.assert_numerically_correct(x, scale)
        expected = torch.tensor([[value / math.sqrt(3.0 + 1e-5) for value in (1, 2, 2)]], dtype=torch.float64)
        torch.testing.assert_close(reference, expected, atol=1e-14, rtol=1e-14)
        reference, eager = self.assert_numerically_correct(x, torch.tensor([2.0, -3.0, 0.0]))
        self.assertGreater(reference[0, 0].item(), 0)
        self.assertLess(reference[0, 1].item(), 0)
        self.assertEqual(eager[0, 2].item(), 0)

    def test_zero_rows_width_one_and_independent_row_reductions(self):
        for x, scale in (
            (torch.zeros(3, 3), torch.tensor([-100.0, 0.0, 100.0])),
            (torch.tensor([[0.0], [1e-4], [-10000.0]]), torch.tensor([-2.0])),
            (
                torch.tensor([[1.0, 2.0, 2.0], [0.0, 0.0, 0.0], [-3.0, 4.0, 12.0]]),
                torch.tensor([0.25, -3.0, 2.0]),
            ),
        ):
            with self.subTest(shape=tuple(x.shape)):
                self.assert_numerically_correct(x, scale)

    def test_non_power_of_two_widths_fixed_random_and_maximum_envelope(self):
        generator = torch.Generator().manual_seed(971)
        for rows, width in ((2, 3), (5, 31), (3, 33), (4, 257), (64, 4096)):
            x = torch.rand(rows, width, generator=generator) * 20000 - 10000
            scale = torch.rand(width, generator=generator) * 200 - 100
            # Exercise inclusive magnitude limits, even in the largest supported shape.
            x[0, 0] = 10000
            x[-1, -1] = -10000
            scale[0] = 100
            scale[-1] = -100
            with self.subTest(rows=rows, width=width):
                self.assert_numerically_correct(x, scale)

    def test_deliberately_wrong_equations_and_tail_are_rejected(self):
        x = torch.tensor([[1.0, 2.0, 2.0], [-3.0, 4.0, 12.0]])
        scale = torch.tensor([2.0, -3.0, 0.5])
        expected = hand_oracle(x, scale).to(torch.float32)
        wrong_tail = expected.clone()
        wrong_tail[:, -1] = 0
        wrong_outputs = {
            "omit_scale": x / torch.sqrt(x.square().mean(dim=1, keepdim=True) + 1e-5),
            "omit_tail_in_reduction": x
            / torch.sqrt(x[:, :-1].square().sum(dim=1, keepdim=True) / x.shape[1] + 1e-5)
            * scale,
            "divide_by_H_minus_one": x
            / torch.sqrt(x.square().sum(dim=1, keepdim=True) / (x.shape[1] - 1) + 1e-5)
            * scale,
            "unwritten_tail": wrong_tail,
        }
        for defect, output in wrong_outputs.items():
            with self.subTest(defect=defect):
                observation = self.check(x, scale, output)
                self.assert_observation(observation, "fail")
                errors = (output.to(torch.float64) - hand_oracle(x, scale)).abs()
                failures = errors > 1e-5 + 1e-4 * hand_oracle(x, scale).abs()
                self.assertEqual(observation["failing_elements"], int(failures.sum().item()))
                self.assertAlmostEqual(observation["max_absolute_error"], errors.max().item(), places=14)
        # Normal-size inputs conceal epsilon placement; these tiny values distinguish it.
        tiny = torch.tensor([[1e-4, 2e-4, -2e-4]])
        weights = torch.ones(3)
        outside_root = tiny / (torch.sqrt(tiny.square().mean(dim=1, keepdim=True)) + 1e-5)
        self.assert_observation(self.check(tiny, weights, outside_root), "fail")

    def test_elementwise_frozen_tolerance_and_unrounded_oracle(self):
        x = torch.tensor([[1.0, 2.0, 2.0]])
        scale = torch.tensor([1.0, -3.0, 0.0])
        expected = hand_oracle(x, scale)
        # Choose neighboring representable FP32 values on each side of the true boundary.
        boundary = expected[0, 0].item() + 1e-5 + 1e-4 * abs(expected[0, 0].item())
        below = torch.tensor(boundary, dtype=torch.float32)
        while below.item() > boundary:
            below = torch.nextafter(below, torch.tensor(-math.inf))
        above = torch.nextafter(below, torch.tensor(math.inf))
        passing = expected.to(torch.float32)
        passing[0, 0] = below
        self.assert_observation(self.check(x, scale, passing), "pass")
        failing = passing.clone()
        failing[0, 0] = above
        observation = self.check(x, scale, failing)
        self.assert_observation(observation, "fail")
        self.assertEqual(observation["failing_elements"], 1)
        self.assertEqual(observation["max_absolute_error"], (failing.double() - expected).abs().max().item())
        zero_boundary = expected.to(torch.float32)
        zero_boundary[0, 2] = 2e-5
        self.assertEqual(self.check(x, scale, zero_boundary)["failing_elements"], 1)
        # These independently chosen FP32 values reverse the verdict if the oracle
        # is rounded before comparison. Exercise both false failure and false pass.
        for value, actual, outcome in (
            (0.0008, 0.24529024958610535, "pass"),
            (0.0013, 0.38026902079582214, "fail"),
        ):
            with self.subTest(unrounded_input=value):
                tiny_x = torch.tensor([[value]])
                tiny_scale = torch.ones(1)
                candidate = torch.tensor([[actual]])
                expected = hand_oracle(tiny_x, tiny_scale)
                exact_pass = bool(
                    ((candidate.double() - expected).abs() <= 1e-5 + 1e-4 * expected.abs()).all()
                )
                rounded = expected.float().double()
                rounded_pass = bool(
                    ((candidate.double() - rounded).abs() <= 1e-5 + 1e-4 * rounded.abs()).all()
                )
                self.assertNotEqual(exact_pass, rounded_pass)
                self.assertEqual(exact_pass, outcome == "pass")
                self.assert_observation(self.check(tiny_x, tiny_scale, candidate), outcome)

    def test_invalid_inputs_raise_value_error_on_all_entry_points(self):
        x, scale = torch.ones(2, 3), torch.ones(3)
        invalid = [
            (None, scale),
            (x, None),
            (x.double(), scale),
            (x.half(), scale),
            (x.to(torch.int64), scale),
            (x, scale.double()),
            (x, scale.half()),
            (x.clone().requires_grad_(), scale),
            (x, scale.clone().requires_grad_()),
            (torch.ones(3), scale),
            (torch.ones(1, 2, 3), scale),
            (x, torch.ones(1, 3)),
            (x, torch.ones(2)),
            (torch.ones(0, 3), scale),
            (torch.ones(65, 3), scale),
            (torch.ones(2, 0), torch.ones(0)),
            (torch.ones(1, 4097), torch.ones(4097)),
            (torch.ones(2, 6)[:, ::2], scale),
            (x, torch.ones(6)[::2]),
            (x.to_sparse(), scale),
            (x, scale.to_sparse()),
            (torch.empty(2, 3, device="meta"), scale),
            (x, torch.empty(3, device="meta")),
            (torch.full((2, 3), 10001.0), scale),
            (torch.full((2, 3), -10001.0), scale),
            (x, torch.full((3,), 101.0)),
            (x, torch.full((3,), -101.0)),
        ]
        for value in (math.nan, math.inf, -math.inf):
            invalid.extend(((torch.full((2, 3), value), scale), (x, torch.full((3,), value))))
        for index, (bad_x, bad_scale) in enumerate(invalid):
            for function in (self.reference, self.eager, self.check):
                with self.subTest(case=index, function=function.__name__), self.assertRaises(ValueError):
                    args = (
                        (bad_x, bad_scale, torch.zeros(2, 3))
                        if function == self.check
                        else (bad_x, bad_scale)
                    )
                    function(*args)

    def test_invalid_outputs_have_reasons_and_null_metrics(self):
        x, scale = torch.ones(2, 3), torch.ones(3)
        invalid = [
            None,
            [[1.0] * 3] * 2,
            torch.ones(2, 3, dtype=torch.float64),
            torch.ones(2, 3, dtype=torch.float16),
            torch.ones(2, 3, dtype=torch.int64),
            torch.ones(3, 2),
            torch.ones(6),
            torch.ones(2, 3, requires_grad=True),
            torch.ones(2, 6)[:, ::2],
            torch.ones(2, 3).to_sparse(),
            torch.empty(2, 3, device="meta"),
            x,
            x.view(2, 3),
        ]
        invalid.extend(torch.full((2, 3), value) for value in (math.nan, math.inf, -math.inf))
        for index, output in enumerate(invalid):
            with self.subTest(case=index):
                observation = self.check(x, scale, output)
                self.assert_observation(observation, "invalid")
                self.assertIsInstance(observation["reason"], str)
                self.assertTrue(observation["reason"])
                self.assertIsNone(observation["failing_elements"])
                self.assertIsNone(observation["max_absolute_error"])
        # A view of scale is also an invalid output, even if its shape is exact.
        self.assert_observation(self.check(torch.ones(1, 3), scale, scale.view(1, 3)), "invalid")
        storage = torch.ones(12)
        # Data pointers differ and regions do not overlap, but storage ownership is shared.
        offset_x, offset_output = storage[:6].view(2, 3), storage[6:].view(2, 3)
        self.assertNotEqual(offset_x.data_ptr(), offset_output.data_ptr())
        self.assert_observation(self.check(offset_x, scale, offset_output), "invalid")

    def test_inputs_bytes_unchanged_and_results_have_independent_storage(self):
        x = torch.tensor([[1.0, 2.0, 2.0], [-3.0, 4.0, 12.0]])
        scale = torch.tensor([2.0, -3.0, 0.0])
        x_bytes = x.view(torch.uint8).clone()
        scale_bytes = scale.view(torch.uint8).clone()
        reference, eager = self.assert_numerically_correct(x, scale)
        storage_ids = [value.untyped_storage().data_ptr() for value in (x, scale, reference, eager)]
        self.assertEqual(len(set(storage_ids)), len(storage_ids))
        self.assertTrue(torch.equal(x.view(torch.uint8), x_bytes))
        self.assertTrue(torch.equal(scale.view(torch.uint8), scale_bytes))
        reference.fill_(23)
        eager.fill_(-42)
        self.assertTrue(torch.equal(x.view(torch.uint8), x_bytes))
        self.assertTrue(torch.equal(scale.view(torch.uint8), scale_bytes))

    def test_exact_digests_contract_identity_and_detached_observation(self):
        x = torch.tensor([[1.0, 2.0, 2.0]])
        scale = torch.tensor([2.0, -3.0, 0.5])
        output = self.eager(x, scale)
        original = self.check(x, scale, output)
        self.assertEqual(original, self.check(x.clone(), scale.clone(), output.clone()))
        saved = copy.deepcopy(original)
        for target in ("x", "scale", "output"):
            changed_x, changed_scale, changed_output = x.clone(), scale.clone(), output.clone()
            tensor = {"x": changed_x, "scale": changed_scale, "output": changed_output}[target]
            # One representable step detects exact bytes, not rounded display numbers.
            tensor.view(-1)[0] = torch.nextafter(tensor.view(-1)[0], torch.tensor(math.inf))
            changed = self.check(changed_x, changed_scale, changed_output)
            key = "output_digest" if target == "output" else "input_digest"
            self.assertNotEqual(original[key], changed[key])
            other_key = "input_digest" if target == "output" else "output_digest"
            self.assertEqual(original[other_key], changed[other_key])
            self.assertEqual(original["contract_digest"], changed["contract_digest"])
        x.fill_(9)
        scale.fill_(7)
        output.fill_(-1)
        self.assertEqual(original, saved)
        self.assert_observation(original, "pass")
        fresh_x = torch.tensor([[1.0, 2.0, 2.0]])
        fresh_scale = torch.tensor([2.0, -3.0, 0.5])
        fresh_output = self.eager(fresh_x, fresh_scale)
        original["inputs"]["x"]["shape"][0] = 999
        self.assertEqual(self.check(fresh_x, fresh_scale, fresh_output), saved)

    def test_subclass_dispatch_is_rejected_before_any_tensor_operation(self):
        class DispatchTrap(torch.Tensor):
            @classmethod
            def __torch_function__(cls, function, types, args=(), kwargs=None):
                raise AssertionError("unsupported subclass dispatch was executed")

        x, scale = torch.ones(2, 3), torch.ones(3)
        subclass_x = torch.Tensor._make_subclass(DispatchTrap, x, False)
        subclass_scale = torch.Tensor._make_subclass(DispatchTrap, scale, False)
        for bad_x, bad_scale in ((subclass_x, scale), (x, subclass_scale)):
            for function in (self.reference, self.eager, self.check):
                with self.subTest(function=function.__name__), self.assertRaises(ValueError):
                    if function == self.check:
                        function(bad_x, bad_scale, torch.ones(2, 3))
                    else:
                        function(bad_x, bad_scale)
        self.assert_observation(self.check(x, scale, subclass_x), "invalid")

    def test_nested_tensors_are_rejected_without_shape_access_errors(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            nested = torch.nested.nested_tensor([torch.tensor([1.0, 2.0]), torch.tensor([3.0])])
        x, scale = torch.ones(2, 3), torch.ones(3)
        for bad_x, bad_scale in ((nested, scale), (x, nested)):
            for function in (self.reference, self.eager, self.check):
                with self.subTest(function=function.__name__), self.assertRaises(ValueError):
                    if function == self.check:
                        function(bad_x, bad_scale, torch.ones(2, 3))
                    else:
                        function(bad_x, bad_scale)
        self.assert_observation(self.check(x, scale, nested), "invalid")

    def test_distinct_storage_objects_with_overlapping_external_bytes_are_invalid(self):
        raw = bytearray(36)
        x = torch.frombuffer(raw, dtype=torch.float32, count=6, offset=0).view(2, 3)
        output = torch.frombuffer(raw, dtype=torch.float32, count=6, offset=12).view(2, 3)
        self.assertNotEqual(x.untyped_storage().data_ptr(), output.untyped_storage().data_ptr())
        self.assert_observation(self.check(x, torch.ones(3), output), "invalid")
        scale = torch.frombuffer(raw, dtype=torch.float32, count=3, offset=0)
        scale_output = torch.frombuffer(raw, dtype=torch.float32, count=3, offset=4).view(1, 3)
        self.assertNotEqual(scale.untyped_storage().data_ptr(), scale_output.untyped_storage().data_ptr())
        self.assert_observation(self.check(torch.zeros(1, 3), scale, scale_output), "invalid")

    def test_lazy_negative_views_bind_logical_bytes_and_signed_zero(self):
        x = torch._neg_view(torch.tensor([[1.0, 2.0, 2.0]]))
        scale = torch._neg_view(torch.tensor([2.0, -3.0, 0.5]))
        self.assertTrue(x.is_neg())
        self.assertTrue(scale.is_neg())
        self.assert_numerically_correct(x, scale)
        eager = self.eager(x, scale)
        output = torch._neg_view(-eager)
        self.assertTrue(output.is_neg())
        observation = self.check(x, scale, output)
        self.assert_observation(observation, "pass")
        self.assertEqual(observation, self.check(x.clone(), scale.clone(), output.clone()))
        positive_zero = torch.zeros(1, 1)
        negative_zero = -positive_zero
        weights = torch.ones(1)
        positive = self.check(positive_zero, weights, positive_zero.clone())
        negative_input = self.check(negative_zero, weights, positive_zero.clone())
        negative_output = self.check(positive_zero, weights, negative_zero.clone())
        self.assertNotEqual(positive["input_digest"], negative_input["input_digest"])
        self.assertNotEqual(positive["output_digest"], negative_output["output_digest"])
        self.assert_observation(negative_input, "pass")
        self.assert_observation(negative_output, "pass")

    def test_counterexample_is_bounded_finite_json(self):
        from compute.rmsnorm import rmsnorm_counterexample

        trace = rmsnorm_counterexample()
        self.assertIsInstance(trace, dict)
        serialized = json.dumps(trace, allow_nan=False)
        self.assertLess(len(serialized.encode()), 100000)
        self.assertEqual(json.loads(serialized), trace)
        self.assertIn("reference", trace)
        self.assertIn("eager", trace)
        self.assert_observation(trace["observations"]["eager"], "pass")
        for defect in ("omitted_scale", "bad_tail", "bad_reduction", "epsilon_outside_root"):
            self.assert_observation(trace["observations"][defect], "fail")
