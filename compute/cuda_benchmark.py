"""Explicit CUDA preflight and correctness-before-timing; never falls back to MPS/CPU."""

import argparse
import json
import platform
import subprocess

from .attention import absolute_mask, require_torch
from evals.validation import count


def preflight():
    try:
        torch = require_torch()
    except RuntimeError as exc:
        return {"status": "skipped", "reason": str(exc), "backend": "CUDA", "fallback": None}
    result = {
        "backend": "CUDA",
        "torch_version": str(torch.__version__),
        "cuda_runtime": torch.version.cuda,
        "python": platform.python_version(),
        "fallback": None,
    }
    if not torch.cuda.is_available():
        return {
            **result,
            "status": "skipped",
            "reason": "CUDA unavailable; no MPS or CPU benchmark substitution",
        }
    result.update(
        status="available",
        device=torch.cuda.get_device_name(0),
        capability=list(torch.cuda.get_device_capability(0)),
    )
    try:
        process = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        result["driver_version"] = process.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        result["driver_version"] = "unavailable"
    return result


def memory_peak_delta(start_allocated, start_reserved, peak_allocated, peak_reserved):
    """Pure accounting: peak counters do not free tensors or cached allocator blocks."""
    for name, value in (
        ("starting allocated", start_allocated),
        ("starting reserved", start_reserved),
        ("peak allocated", peak_allocated),
        ("peak reserved", peak_reserved),
    ):
        count(value, name)
    if peak_allocated < start_allocated or peak_reserved < start_reserved:
        raise ValueError("memory peak cannot be below its starting residency")
    return {
        "starting_allocated_bytes": start_allocated,
        "starting_reserved_bytes": start_reserved,
        "peak_allocated_bytes": peak_allocated,
        "peak_reserved_bytes": peak_reserved,
        "incremental_peak_allocated_bytes": peak_allocated - start_allocated,
        "incremental_peak_reserved_bytes": peak_reserved - start_reserved,
    }


def benchmark(
    *,
    batch=1,
    query_heads=4,
    kv_heads=2,
    cached=16,
    appended=4,
    dim=16,
    warmup=3,
    repeats=10,
    seed=7,
    backend="math",
):
    for field, value in (
        ("batch", batch),
        ("query_heads", query_heads),
        ("kv_heads", kv_heads),
        ("appended", appended),
        ("dim", dim),
        ("repeats", repeats),
    ):
        count(value, field, 1)
    count(cached, "cached")
    count(warmup, "warmup")
    count(seed, "seed")
    if query_heads % kv_heads or backend not in {"math", "flash"}:
        raise ValueError("invalid benchmark contract")
    info = preflight()
    if info["status"] != "available":
        return info
    torch = require_torch()
    from torch.nn.attention import SDPBackend, sdpa_kernel

    selected = SDPBackend.MATH if backend == "math" else SDPBackend.FLASH_ATTENTION
    dtype = torch.float32 if backend == "math" else torch.float16
    generator = torch.Generator(device="cuda").manual_seed(seed)
    q = torch.randn(batch, query_heads, appended, dim, device="cuda", dtype=dtype, generator=generator)
    k = torch.randn(batch, kv_heads, cached + appended, dim, device="cuda", dtype=dtype, generator=generator)
    v = torch.randn(batch, kv_heads, cached + appended, dim, device="cuda", dtype=dtype, generator=generator)
    ek, ev = k.repeat_interleave(query_heads // kv_heads, 1), v.repeat_interleave(query_heads // kv_heads, 1)
    mask = absolute_mask(appended, cached + appended, cached, device="cuda")

    def eager():
        logits = q @ ek.transpose(-1, -2) / dim**0.5
        return torch.softmax(logits.masked_fill(~mask, -torch.inf), -1) @ ev

    def sdpa():
        with sdpa_kernel(selected):
            return torch.nn.functional.scaled_dot_product_attention(
                q, ek, ev, attn_mask=mask, dropout_p=0.0, is_causal=False
            )

    reference = (
        torch.softmax(
            (q.double() @ ek.double().transpose(-1, -2) / dim**0.5).masked_fill(~mask, -torch.inf), -1
        )
        @ ev.double()
    ).to(dtype)
    tolerances = {"atol": 1e-5, "rtol": 1e-4} if dtype == torch.float32 else {"atol": 5e-3, "rtol": 5e-3}
    try:
        for sample in range(3):
            if sample:
                q = torch.randn(
                    batch, query_heads, appended, dim, device="cuda", dtype=dtype, generator=generator
                )
                k = torch.randn(
                    batch, kv_heads, cached + appended, dim, device="cuda", dtype=dtype, generator=generator
                )
                v = torch.randn(
                    batch, kv_heads, cached + appended, dim, device="cuda", dtype=dtype, generator=generator
                )
                ek, ev = (
                    k.repeat_interleave(query_heads // kv_heads, 1),
                    v.repeat_interleave(query_heads // kv_heads, 1),
                )
                reference = (
                    torch.softmax(
                        (q.double() @ ek.double().transpose(-1, -2) / dim**0.5).masked_fill(
                            ~mask, -torch.inf
                        ),
                        -1,
                    )
                    @ ev.double()
                ).to(dtype)
            for function in (eager, sdpa):
                torch.testing.assert_close(function(), reference, **tolerances)
        torch.cuda.synchronize()
    except RuntimeError as exc:
        return {
            **info,
            "status": "unsupported",
            "selected_backend": backend,
            "reason": str(exc),
            "fallback": None,
        }
    results = {}
    for name, function in (("eager", eager), ("sdpa", sdpa)):
        for _ in range(warmup):
            warm_output = function()
            del warm_output
        torch.cuda.synchronize()
        starting_allocated = torch.cuda.memory_allocated()
        starting_reserved = torch.cuda.memory_reserved()
        torch.cuda.reset_peak_memory_stats()
        timings = []
        for iteration in range(repeats):
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            start.record()
            output = function()
            end.record()
            end.synchronize()
            timings.append(start.elapsed_time(end))
            try:
                if iteration == repeats - 1:
                    # Capture peaks before error arithmetic allocates scratch.
                    memory = memory_peak_delta(
                        starting_allocated,
                        starting_reserved,
                        torch.cuda.max_memory_allocated(),
                        torch.cuda.max_memory_reserved(),
                    )
                    max_error = float((output - reference).abs().max())
            finally:
                # Never retain a prior output across another RHS evaluation or arm.
                del output
        torch.cuda.synchronize()
        results[name] = {"raw_milliseconds": timings, **memory, "max_absolute_error": max_error}
    return {
        **info,
        "status": "measured",
        "selected_backend": backend,
        "seed": seed,
        "input_dtype": str(dtype),
        "reference_accumulation_dtype": "float64",
        "candidate_accumulation_dtype": "backend-dependent; not inferred from Python API",
        "correctness_tolerance": tolerances,
        "warmup": warmup,
        "repeats": repeats,
        "correctness_checks_before_timing": 3,
        "inputs": {
            name: {"shape": list(x.shape), "stride": list(x.stride()), "bytes": x.numel() * x.element_size()}
            for name, x in (("Q", q), ("K", k), ("V", v))
        },
        "timing_boundary": "CUDA events around attention only; excludes input transfers, GQA expansion, reference, compilation, and Python host overhead",
        "physical_gqa_expansion_before_timing": True,
        "allocator_policy": "per-arm warmup; outputs released before every next sample/arm; caching allocator reserved blocks retained across repeats/arms, no empty_cache; starting live inputs, expanded KV, mask and float64-derived reference retained and reported in baseline",
        "memory_boundary": "peak sampled before error scratch; incremental peak subtracts starting live allocated/reserved residency; warm reserved-cache delta is not fresh-device capacity",
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--backend", choices=("math", "flash"), default="math")
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            preflight() if args.preflight else benchmark(backend=args.backend, repeats=args.repeats), indent=2
        )
    )
