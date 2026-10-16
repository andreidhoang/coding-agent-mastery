"""One complete tiny CPU tensor/cache/action trace plus a separate CUDA preflight."""

import json
import math

from .attention import counterexample
from .cache import CacheIdentity, PrefixCache, kv_bytes
from .cuda_benchmark import preflight
from .trajectory import Trajectory, masked_objective


def main():
    identity = CacheIdentity("toy-v1", "tokens-v1", "template-v1", "none", "tenant-a", "BHTD", "float32")
    cache = PrefixCache(block_tokens=2, capacity_blocks=3)
    first = cache.acquire("request-a", [1, 2, 3, 4, 5], identity)
    second = cache.acquire("request-b", [1, 2, 3, 4, 6], identity)
    t = Trajectory(
        (7, 8, 9),
        (7, 8, 9),
        ("action", "observation", "padding"),
        (1, 0, 0),
        (math.log(0.5), math.log(0.1), math.log(0.1)),
        (math.log(0.75), math.log(0.9), math.log(0.9)),
        1,
        1,
        "toy-v1",
        "tokens-v1",
        "fixture-v1",
        1.0,
        "synthetic-grader",
        "completed",
    )
    print(
        json.dumps(
            {
                "evidence": "AI-written CPU reference; synthetic fixtures; no model training",
                "attention": counterexample(),
                "kv": kv_bytes(layers=2, batch=1, tokens=4, kv_heads=1, head_dim=2, element_bytes=2),
                "prefix_cache": [first, second],
                "offline_action_loss": masked_objective(t, 1.0),
                "cuda": preflight(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
