"""Integer micro-USD exposure for explicitly frozen provider rate envelopes.

Provider context-window bounds and rates are operator-supplied evidence, not
guessed from a model name. No live rates or model defaults are embedded here.
"""

from __future__ import annotations
from .contracts import strict_int


class ProviderEnvelope:
    FIELDS = {
        "schema",
        "unit",
        "rate_id",
        "model",
        "input_token_bound",
        "max_output_tokens",
        "input_per_million",
        "output_per_million",
        "cache_read_per_million",
        "cache_write_per_million",
        "bound_evidence",
        "max_request_bytes",
    }

    def __init__(self, frozen: dict, model: str):
        if not isinstance(frozen, dict) or set(frozen) != self.FIELDS:
            raise ValueError("complete frozen provider envelope required")
        if frozen["schema"] != 1 or frozen["unit"] != "micro_usd" or frozen["model"] != model:
            raise ValueError("rate unit/schema/model mismatch")
        if not all(isinstance(frozen[k], str) and frozen[k] for k in ("rate_id", "bound_evidence")):
            raise ValueError("rate and enforceable bound evidence identities required")
        self.data = dict(frozen)
        for name in self.FIELDS - {"unit", "rate_id", "model", "bound_evidence"}:
            strict_int(
                frozen[name],
                name,
                1 if name in {"max_output_tokens", "input_token_bound", "max_request_bytes"} else 0,
            )
        if frozen["max_output_tokens"] > 32768:
            raise ValueError("output cap exceeds supported adapter bound")

    @property
    def bound_units(self) -> int:
        f = self.data
        numerator = f["input_token_bound"] * max(
            f["input_per_million"], f["cache_read_per_million"], f["cache_write_per_million"]
        )
        numerator += f["max_output_tokens"] * f["output_per_million"]
        return (numerator + 999999) // 1000000

    def charge(self, usage: dict) -> int:
        f = self.data
        categories = {
            "input_tokens": "input_per_million",
            "output_tokens": "output_per_million",
            "cache_read_input_tokens": "cache_read_per_million",
            "cache_creation_input_tokens": "cache_write_per_million",
        }
        numerator = 0
        for category, price in categories.items():
            count = usage.get(category, 0)
            strict_int(count, category)
            numerator += count * f[price]
        return (numerator + 999999) // 1000000

    def within_token_bounds(self, usage: dict) -> bool:
        inputs = sum(
            usage.get(k, 0)
            for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        )
        return (
            inputs <= self.data["input_token_bound"]
            and usage["output_tokens"] <= self.data["max_output_tokens"]
        )
