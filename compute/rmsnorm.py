"""NV-S0: independent CPU RMSNorm arithmetic and advisory byte-bound observations."""

import json
import math
import sys

from evals.validation import count
from service.artifacts import canonical_bytes, digest_bytes, digest_json

from .attention import require_torch


_EPSILON = 1e-5
_ATOL = 1e-5
_RTOL = 1e-4
_SCHEMA_VERSION = "nv-s0-observation-v1"
_CONTRACT_VERSION = "nv-s0-rmsnorm-cpu-fp32-v1"
_ORACLE_VERSION = "python-float64-fsum-v1"


def _contract():
    # Return owned data, so changing a returned observation cannot change policy.
    return {
        "version": _CONTRACT_VERSION,
        "equation": "x[r,h] / sqrt(fsum(x[r,j]**2)/H + epsilon) * scale[h]",
        "epsilon": _EPSILON,
        "atol": _ATOL,
        "rtol": _RTOL,
        "rows": [1, 64],
        "width": [1, 4096],
        "max_abs_x": 10000,
        "max_abs_scale": 100,
        "dtype": "torch.float32",
        "device": "cpu",
        "layout": "torch.strided",
        "contiguous": True,
        "inference_only": True,
        "output_independent_storage": True,
        "oracle_version": _ORACLE_VERSION,
    }


def _tensor_reason(value, name, shape=None):
    torch = require_torch()
    # Subclasses could execute supplied __torch_function__ code during validation.
    if type(value) is not torch.Tensor:
        return f"{name} must be an exact torch.Tensor"
    if value.is_nested:
        return f"{name} must be a dense tensor"
    if value.device.type != "cpu" or value.layout != torch.strided:
        return f"{name} must use CPU strided layout"
    if value.dtype != torch.float32:
        return f"{name} must be float32"
    if not value.is_contiguous():
        return f"{name} must be contiguous"
    if value.requires_grad:
        return f"{name} must not require gradients (inference only)"
    if shape is not None and tuple(value.shape) != shape:
        return f"{name} shape must be {list(shape)}"
    return None


def _validate_inputs(x, scale):
    torch = require_torch()
    for name, value in (("x", x), ("scale", scale)):
        reason = _tensor_reason(value, name)
        if reason:
            raise ValueError(reason)
    if x.ndim != 2:
        raise ValueError("x must have rank 2 [R,H]")
    rows, width = x.shape
    count(rows, "R", 1)
    count(width, "H", 1)
    if rows > 64 or width > 4096:
        raise ValueError("x dimensions exceed R<=64, H<=4096")
    if tuple(scale.shape) != (width,):
        raise ValueError("scale must have shape [H]")
    for name, value, bound in (("x", x, 10000), ("scale", scale, 100)):
        if not bool(torch.isfinite(value).all()):
            raise ValueError(f"{name} must be finite")
        if bool((value.abs() > bound).any()):
            raise ValueError(f"{name} exceeds absolute bound {bound}")


def rmsnorm_reference(x, scale):
    """Independent Python-float oracle; never round its result to FP32."""
    _validate_inputs(x, scale)
    torch = require_torch()
    rows = x.tolist()  # Python floats represent these FP32 values exactly.
    weights = scale.tolist()
    result = []
    for row in rows:
        mean_square = math.fsum(value * value for value in row) / len(row)
        denominator = math.sqrt(mean_square + _EPSILON)
        result.append([value / denominator * weight for value, weight in zip(row, weights)])
    return torch.tensor(result, dtype=torch.float64, device="cpu")


def rmsnorm_eager(x, scale):
    """FP32 square, row reduction, normalization and broadcast scaling."""
    _validate_inputs(x, scale)
    torch = require_torch()
    with torch.no_grad():
        mean_square = (x * x).mean(dim=1, keepdim=True)
        return x / torch.sqrt(mean_square + _EPSILON) * scale


def _tensor_record(value):
    metadata = {
        "shape": list(value.shape),
        "stride": list(value.stride()),
        "dtype": str(value.dtype),
        "device": str(value.device),
        "layout": str(value.layout),
        "byte_order": sys.byteorder,
        "byte_length": value.numel() * value.element_size(),
    }
    # Hash logical element bytes, including signed zero. Resolving a lazy negative
    # view creates a temporary only; reading raw backing storage would hash wrong values.
    raw = bytes(value.detach().resolve_neg().reshape(-1).view(require_torch().uint8).tolist())
    return {**metadata, "digest": digest_bytes(canonical_bytes(metadata) + b"\0" + raw)}


def check_rmsnorm(x, scale, output):
    """Compare supplied bytes, not an executable; never issue an acceptance receipt."""
    _validate_inputs(x, scale)
    torch = require_torch()
    contract = _contract()
    inputs = {"x": _tensor_record(x), "scale": _tensor_record(scale)}
    observation = {
        "schema_version": _SCHEMA_VERSION,
        "contract_version": _CONTRACT_VERSION,
        "oracle_version": _ORACLE_VERSION,
        "contract": contract,
        "contract_digest": digest_json(contract),
        "input_digest": digest_json(inputs),
        "inputs": inputs,
        "output": None,
        "output_digest": None,
        "atol": _ATOL,
        "rtol": _RTOL,
        "outcome": "invalid",
        "reason": None,
        "failing_elements": None,
        "max_absolute_error": None,
        "evidence": "local CPU tensor observation; executable provenance unestablished",
    }
    reason = _tensor_reason(output, "output", tuple(x.shape))
    if reason:
        observation["reason"] = reason
        return observation
    observation["output"] = _tensor_record(output)
    observation["output_digest"] = observation["output"]["digest"]
    # Whole storage ranges reject offset views and overlapping external buffers,
    # including separate torch.frombuffer wrappers with different storage bases.
    output_storage = output.untyped_storage()
    output_start = output_storage.data_ptr()
    output_end = output_start + output_storage.nbytes()
    for value in (x, scale):
        input_storage = value.untyped_storage()
        input_start = input_storage.data_ptr()
        if output_start < input_start + input_storage.nbytes() and input_start < output_end:
            observation["reason"] = "output must have independent input storage"
            return observation
    if not bool(torch.isfinite(output).all()):
        observation["reason"] = "output must be finite"
        return observation
    reference = rmsnorm_reference(x, scale)
    absolute_error = (output.to(torch.float64) - reference).abs()
    failing = int((absolute_error > _ATOL + _RTOL * reference.abs()).sum())
    observation.update(
        outcome="fail" if failing else "pass",
        reason="elementwise tolerance exceeded" if failing else "within elementwise tolerance",
        failing_elements=failing,
        max_absolute_error=float(absolute_error.max()),
    )
    return observation


def rmsnorm_counterexample():
    """Small CPU trace: scaling, tail/reduction and epsilon-placement defects."""
    torch = require_torch()
    x = torch.tensor([[1, 2, 2], [1e-4, 2e-4, 2e-4]], dtype=torch.float32)
    scale = torch.tensor([1, -2, 0.5], dtype=torch.float32)
    reference = rmsnorm_reference(x, scale)
    eager = rmsnorm_eager(x, scale)
    squared = x * x
    mean_square = squared.mean(dim=1, keepdim=True)
    denominator = torch.sqrt(mean_square + _EPSILON)
    candidates = {
        "eager": eager,
        "omitted_scale": x / denominator,
        "bad_tail": x / torch.sqrt(squared[:, :-1].sum(dim=1, keepdim=True) / 3 + _EPSILON) * scale,
        "bad_reduction": x / torch.sqrt(squared.sum(dim=1, keepdim=True) + _EPSILON) * scale,
        "epsilon_outside_root": x / (torch.sqrt(mean_square) + _EPSILON) * scale,
    }
    return {
        "evidence": "CPU reference teaching trace; GPU execution and performance unmeasured",
        "x": {**_tensor_record(x), "values": x.tolist()},
        "scale": {**_tensor_record(scale), "values": scale.tolist()},
        "squared": squared.tolist(),
        "mean_square": mean_square.tolist(),
        "denominator": denominator.tolist(),
        "reference": {"dtype": str(reference.dtype), "values": reference.tolist()},
        "eager": {"dtype": str(eager.dtype), "values": eager.tolist()},
        "observations": {name: check_rmsnorm(x, scale, value) for name, value in candidates.items()},
    }


if __name__ == "__main__":
    print(json.dumps(rmsnorm_counterexample(), indent=2, allow_nan=False))
