"""Ideal KV bytes and full-block prefix identity/ownership model; not an engine allocator."""

import copy
import hashlib
import json
from dataclasses import dataclass

from evals.validation import count


def kv_bytes(
    *, layers, batch, tokens, kv_heads, head_dim, element_bytes, value_head_dim=None, block_tokens=1
):
    for field, value in (
        ("layers", layers),
        ("batch", batch),
        ("tokens", tokens),
        ("kv_heads", kv_heads),
        ("head_dim", head_dim),
        ("element_bytes", element_bytes),
        ("block_tokens", block_tokens),
    ):
        count(value, field, 1)
    value_head_dim = head_dim if value_head_dim is None else value_head_dim
    count(value_head_dim, "value_head_dim", 1)
    bytes_per_token = layers * batch * kv_heads * (head_dim + value_head_dim) * element_bytes
    rounded_tokens = ((tokens + block_tokens - 1) // block_tokens) * block_tokens
    return {
        "ideal_bytes": tokens * bytes_per_token,
        "rounded_block_bytes": rounded_tokens * bytes_per_token,
        "padding_bytes": (rounded_tokens - tokens) * bytes_per_token,
        "bytes_per_token": bytes_per_token,
        "excludes": [
            "weights",
            "workspace",
            "activation buffers",
            "graphs",
            "fragmentation",
            "headroom",
            "shard replication",
        ],
    }


@dataclass(frozen=True)
class CacheIdentity:
    model_revision: str
    tokenizer_revision: str
    template_revision: str
    adapter_revision: str
    namespace: str
    kv_layout: str
    dtype: str

    def validate(self):
        if any(not isinstance(v, str) or not v for v in vars(self).values()):
            raise ValueError("all immutable cache identities required; use 'none' for no adapter")


@dataclass
class Block:
    key: str
    tokens: tuple[int, ...]
    parent: str
    owners: set[str]
    touched: int


class PrefixCache:
    def __init__(self, *, block_tokens, capacity_blocks):
        count(block_tokens, "block_tokens", 1)
        count(capacity_blocks, "capacity_blocks")
        self.block_tokens, self.capacity_blocks = block_tokens, capacity_blocks
        self.blocks, self.requests, self.clock = {}, {}, 0
        self.trace = []

    def acquire(self, owner, tokens, identity):
        identity.validate()
        tokens = tuple(tokens)
        for token in tokens:
            count(token, "token ID")
        if not isinstance(owner, str) or not owner or owner in self.requests:
            raise ValueError("invalid owner or tokens")
        complete = len(tokens) // self.block_tokens
        if complete > self.capacity_blocks:
            raise RuntimeError("prefix exceeds block capacity")
        before = copy.deepcopy((self.blocks, self.requests, self.clock, self.trace))
        parent, keys, hits, misses, evictions = "root", [], 0, 0, []
        try:
            for i in range(complete):
                block_tokens = tokens[i * self.block_tokens : (i + 1) * self.block_tokens]
                raw = json.dumps(
                    {"parent": parent, "tokens": block_tokens, "identity": vars(identity)}, sort_keys=True
                ).encode()
                key = hashlib.sha256(raw).hexdigest()
                self.clock += 1
                if key in self.blocks:
                    hits += 1
                else:
                    misses += 1
                    if len(self.blocks) >= self.capacity_blocks:
                        eligible = [b for b in self.blocks.values() if not b.owners]
                        if not eligible:
                            raise RuntimeError(
                                "all cache blocks pinned; cannot infer free capacity from lease expiry"
                            )
                        victim = min(eligible, key=lambda b: (b.touched, b.key))
                        del self.blocks[victim.key]
                        evictions.append(victim.key)
                    self.blocks[key] = Block(key, block_tokens, parent, set(), self.clock)
                block = self.blocks[key]
                block.owners.add(owner)
                block.touched = self.clock
                keys.append(key)
                parent = key
            self.requests[owner] = tuple(keys)
        except Exception:
            self.blocks, self.requests, self.clock, self.trace = before
            raise
        record = {
            "owner": owner,
            "hits": hits,
            "misses": misses,
            "evictions": evictions,
            "keys": keys,
            "cached_tokens": complete * self.block_tokens,
            "uncached_tail_tokens": len(tokens) % self.block_tokens,
            "resident_blocks": len(self.blocks),
            "evidence": "synthetic full-block cache model",
        }
        self.trace.append(copy.deepcopy(record))
        return record

    def release(self, owner):
        if owner not in self.requests:
            raise ValueError("unknown owner")
        for key in self.requests.pop(owner):
            self.blocks[key].owners.remove(owner)
        self.trace.append({"event": "release", "owner": owner})


if __name__ == "__main__":
    print(
        json.dumps(kv_bytes(layers=2, batch=1, tokens=4, kv_heads=1, head_dim=2, element_bytes=2), indent=2)
    )
