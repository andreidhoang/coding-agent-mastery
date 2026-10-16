"""H12: exact cached absolute-position attention with explicit physical GQA expansion."""

import math

from evals.validation import count


def require_torch():
    try:
        import torch

        return torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch unavailable: install the compute extra; no substitute tensor backend"
        ) from exc


def validate(q, k, v, cached_length):
    torch = require_torch()
    if q.ndim != 4 or k.ndim != 4 or v.ndim != 4 or any(x.numel() == 0 for x in (q, k, v)):
        raise ValueError("Q/K/V must be nonempty [B,H,T,D] tensors")
    b, hq, u, d = q.shape
    bk, hkv, t, dk = k.shape
    if (b, hkv, t) != tuple(v.shape[:3]) or b != bk or d != dk or hq % hkv:
        raise ValueError("incompatible batch, heads, tokens or dimensions")
    count(cached_length, "cached_length")
    if t != cached_length + u:
        raise ValueError("K/V length must equal cached prefix plus appended queries")
    if any(x.dtype != q.dtype or x.device != q.device or not x.is_floating_point() for x in (q, k, v)):
        raise ValueError("Q/K/V floating dtype and device must match")
    if any(not bool(torch.isfinite(x).all()) for x in (q, k, v)):
        raise ValueError("nonfinite inputs")


def absolute_mask(query_length, key_length, cached_length, *, device="cpu"):
    count(query_length, "query_length", 1)
    count(key_length, "key_length", 1)
    count(cached_length, "cached_length")
    torch = require_torch()
    if key_length != cached_length + query_length:
        raise ValueError("invalid cached mask dimensions")
    # True means allowed for torch SDPA. Local query i is global token C+i.
    return (
        torch.arange(key_length, device=device)[None, :]
        <= (cached_length + torch.arange(query_length, device=device))[:, None]
    )


def tensor_ledger(tensor):
    return {
        "shape": list(tensor.shape),
        "stride": list(tensor.stride()),
        "dtype": str(tensor.dtype),
        "device": str(tensor.device),
        "elements": tensor.numel(),
        "logical_bytes": tensor.numel() * tensor.element_size(),
        "storage_bytes": tensor.untyped_storage().nbytes(),
        "contiguous": tensor.is_contiguous(),
        "values": tensor.detach().cpu().tolist(),
    }


def eager_attention(q, k, v, cached_length=0):
    """Derive scores/probabilities in float64; cast final output to original input dtype."""
    torch = require_torch()
    validate(q, k, v, cached_length)
    group = q.shape[1] // k.shape[1]
    expanded_k = k.repeat_interleave(group, dim=1).to(torch.float64)
    expanded_v = v.repeat_interleave(group, dim=1).to(torch.float64)
    scores = q.to(torch.float64) @ expanded_k.transpose(-1, -2) / math.sqrt(q.shape[-1])
    mask = absolute_mask(q.shape[2], k.shape[2], cached_length, device=q.device)
    probabilities = torch.softmax(scores.masked_fill(~mask, -torch.inf), dim=-1)
    output = (probabilities @ expanded_v).to(q.dtype)
    return output, {
        "evidence": "eager tensor reference",
        "cached_length": cached_length,
        "head_mapping": [h // group for h in range(q.shape[1])],
        "gqa_expansion": "physical reference convenience; engines may index logical KV heads",
        "accumulation_dtype": "torch.float64",
        "Q": tensor_ledger(q),
        "K": tensor_ledger(k),
        "V": tensor_ledger(v),
        "expanded_K": tensor_ledger(expanded_k),
        "scores": tensor_ledger(scores),
        "allowed_mask": tensor_ledger(mask),
        "probabilities": tensor_ledger(probabilities),
        "output": tensor_ledger(output),
    }


def scalar_attention(q, k, v, cached_length=0):
    """Independent scalar dot/softmax/sum oracle; no shared mask or GQA expansion helper."""
    torch = require_torch()
    validate(q, k, v, cached_length)
    b, hq, u, d = q.shape
    output = torch.zeros((b, hq, u, v.shape[-1]), dtype=q.dtype, device=q.device)
    for batch in range(b):
        for head in range(hq):
            kv_head = head // (hq // k.shape[1])
            for i in range(u):
                allowed = range(cached_length + i + 1)
                logits = [
                    sum(float(q[batch, head, i, x]) * float(k[batch, kv_head, j, x]) for x in range(d))
                    / math.sqrt(d)
                    for j in allowed
                ]
                maximum = max(logits)
                weights = [math.exp(x - maximum) for x in logits]
                denominator = sum(weights)
                for x in range(v.shape[-1]):
                    output[batch, head, i, x] = (
                        sum(w * float(v[batch, kv_head, j, x]) for j, w in zip(allowed, weights))
                        / denominator
                    )
    return output


def sdpa_attention(q, k, v, cached_length=0):
    torch = require_torch()
    validate(q, k, v, cached_length)
    group = q.shape[1] // k.shape[1]
    return torch.nn.functional.scaled_dot_product_attention(
        q,
        k.repeat_interleave(group, 1),
        v.repeat_interleave(group, 1),
        attn_mask=absolute_mask(q.shape[2], k.shape[2], cached_length, device=q.device),
        is_causal=False,
        dropout_p=0.0,
    )


def counterexample():
    torch = require_torch()
    q = torch.zeros(1, 1, 1, 1)
    k = torch.zeros(1, 1, 4, 1)
    v = torch.tensor([2.0, 4.0, 8.0, 10.0]).reshape(1, 1, 4, 1)
    output, ledger = eager_attention(q, k, v, 3)
    wrong = torch.nn.functional.scaled_dot_product_attention(q, k, v, is_causal=True, dropout_p=0)
    return {
        "evidence": "CPU measured semantics when executed",
        "hand_derived_expected": 6.0,
        "scalar": scalar_attention(q, k, v, 3).item(),
        "explicit_mask_sdpa": sdpa_attention(q, k, v, 3).item(),
        "eager": output.item(),
        "wrong_upper_left_causal": wrong.item(),
        "ledger": ledger,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(counterexample(), indent=2))
