"""Synthetic discrete-event DAG and open-loop serving models, never measured service latency."""

import heapq
import math
from dataclasses import dataclass
from statistics import mean

from .validation import count, duration, finite_real


@dataclass(frozen=True)
class Node:
    node_id: str
    seconds: float
    dependencies: tuple[str, ...] = ()
    cpu_units: int = 1
    model_calls: int = 0
    patch_slots: int = 1


def simulate_dag(nodes, *, n, cpu_capacity=4, model_capacity=2):
    count(n, "workers", 1)
    count(cpu_capacity, "cpu_capacity", 1)
    count(model_capacity, "model_capacity", 1)
    if n not in (1, 2, 4):
        raise ValueError("invalid capacity")
    by_id = {node.node_id: node for node in nodes}
    if not nodes or len(by_id) != len(nodes):
        raise ValueError("empty/duplicate nodes")
    for node in nodes:
        finite_real(node.seconds, "node seconds", positive=True)
        if any(d not in by_id for d in node.dependencies):
            raise ValueError("invalid dependency")
        for field in ("cpu_units", "model_calls", "patch_slots"):
            count(getattr(node, field), field)
        if node.cpu_units > cpu_capacity or node.model_calls > model_capacity or node.patch_slots > n:
            raise ValueError("node cannot fit envelope")
    # Structural longest-path recurrence catches cycles independently of scheduler.
    lengths, paths, visiting = {}, {}, set()

    def longest(key):
        if key in visiting:
            raise ValueError("cyclic DAG")
        if key not in lengths:
            visiting.add(key)
            deps = by_id[key].dependencies
            parent = max(deps, key=lambda d: (longest(d), d)) if deps else None
            lengths[key] = finite_real(
                by_id[key].seconds + (lengths[parent] if parent else 0), "critical path", minimum=0
            )
            paths[key] = (paths[parent] if parent else []) + [key]
            visiting.remove(key)
        return lengths[key]

    for key in by_id:
        longest(key)
    terminal = max(by_id, key=lambda k: (lengths[k], k))
    now, pending, running, completed, trace = 0.0, set(by_id), [], {}, []
    active, blocked_by, causal_paths = {}, {k: set() for k in by_id}, {}
    while pending or running:
        used = [
            sum(getattr(by_id[k], field) for k in active)
            for field in ("cpu_units", "model_calls", "patch_slots")
        ]
        for key in sorted(pending):
            node = by_id[key]
            resources = [node.cpu_units, node.model_calls, node.patch_slots]
            if all(d in completed for d in node.dependencies) and all(
                u + r <= c for u, r, c in zip(used, resources, (cpu_capacity, model_capacity, n))
            ):
                finish = finite_real(now + node.seconds, "node finish", minimum=0)
                heapq.heappush(running, (finish, key))
                predecessors = set(node.dependencies) | blocked_by[key]
                predecessors = {p for p in predecessors if p in completed}
                causal_parent = (
                    max(predecessors, key=lambda p: (completed[p]["finished_at"], p))
                    if predecessors
                    else None
                )
                causal_paths[key] = (causal_paths[causal_parent] if causal_parent else []) + [key]
                active[key] = {
                    "started_at": now,
                    "finished_at": finish,
                    "dependency_ready_at": max(
                        (completed[d]["finished_at"] for d in node.dependencies), default=0
                    ),
                    "resource_predecessors": sorted(blocked_by[key]),
                    "causal_parent": causal_parent,
                }
                pending.remove(key)
                used = [u + r for u, r in zip(used, resources)]
                trace.append(
                    {
                        "event": "start",
                        "node_id": key,
                        "at": now,
                        "resources_used": dict(zip(("cpu", "model", "patch_slots"), used)),
                        "dependencies": list(node.dependencies),
                    }
                )
            elif all(d in completed for d in node.dependencies):
                for field, needed, total, capacity in zip(
                    ("cpu_units", "model_calls", "patch_slots"),
                    resources,
                    used,
                    (cpu_capacity, model_capacity, n),
                ):
                    if total + needed > capacity:
                        blocked_by[key].update(k for k in active if getattr(by_id[k], field) > 0)
        if not running:
            raise ValueError("unschedulable graph")
        now = running[0][0]
        while running and running[0][0] == now:
            finish, key = heapq.heappop(running)
            completed[key] = active.pop(key)
            used = [
                sum(getattr(by_id[k], field) for k in active)
                for field in ("cpu_units", "model_calls", "patch_slots")
            ]
            trace.append(
                {
                    "event": "finish",
                    "node_id": key,
                    "at": finish,
                    "resources_used": dict(zip(("cpu", "model", "patch_slots"), used)),
                }
            )
    actual_terminal = max(completed, key=lambda k: (completed[k]["finished_at"], k))
    return {
        "evidence": "synthetic discrete-event simulation",
        "n": n,
        "envelope": {"cpu": cpu_capacity, "model": model_capacity, "patch_slots": n},
        "makespan_seconds": now,
        "dependency_critical_path_seconds": lengths[terminal],
        "dependency_critical_path": paths[terminal],
        "realized_critical_path": causal_paths[actual_terminal],
        "realized_critical_path_seconds": sum(by_id[k].seconds for k in causal_paths[actual_terminal]),
        "work_seconds": finite_real(sum(node.seconds for node in nodes), "aggregate work", minimum=0),
        "nodes": completed,
        "trace": trace,
        "limitations": "Durations are inputs. No model quality, physical CPU execution or sandbox isolation is measured.",
    }


@dataclass(frozen=True)
class Arrival:
    request_id: str
    at: float
    prompt_tokens: int
    output_tokens: int
    tool_gap_seconds: float = 0
    appended_tokens: int = 0
    prefix_identity: str = ""


def replay_serving(
    arrivals,
    *,
    n,
    model_capacity=1,
    queue_limit=8,
    prefill_tokens_per_second=100,
    decode_tokens_per_second=20,
    cache_capacity_tokens=1000,
):
    """FIFO admission, independent model slots, retained sandbox through tool idle, LRU warm prefixes.

    The full arrival stream is scheduled before service starts (open loop).
    Cache residency is a simplified token-level model, distinct from full-block PrefixCache.
    """
    count(n, "workers", 1)
    count(model_capacity, "model_capacity", 1)
    count(queue_limit, "queue_limit")
    count(cache_capacity_tokens, "cache_capacity_tokens")
    finite_real(prefill_tokens_per_second, "prefill rate", positive=True)
    finite_real(decode_tokens_per_second, "decode rate", positive=True)
    if n not in (1, 2, 4):
        raise ValueError("invalid serving worker count")
    arrivals = list(arrivals)
    if len({a.request_id for a in arrivals}) != len(arrivals):
        raise ValueError("duplicate request")
    for a in arrivals:
        finite_real(a.at, "arrival time", minimum=0)
        finite_real(a.tool_gap_seconds, "tool gap", minimum=0)
        for field in ("prompt_tokens", "output_tokens", "appended_tokens"):
            count(getattr(a, field), field)
        if not isinstance(a.request_id, str) or not a.request_id or not isinstance(a.prefix_identity, str):
            raise ValueError("request and prefix identities must be strings")
        # Validate both possible cold histories before publishing any trace.
        duration(
            a.prompt_tokens + a.output_tokens + a.appended_tokens,
            prefill_tokens_per_second,
            "cold history prefill",
        )
        duration(a.output_tokens, decode_tokens_per_second, "decode")
    event_heap, counter = [], 0

    def event(at, kind, payload):
        nonlocal counter
        finite_real(at, "event time", minimum=0)
        counter += 1
        heapq.heappush(event_heap, (at, int(kind == "arrival"), counter, kind, payload))

    for a in sorted(arrivals, key=lambda x: (x.at, x.request_id)):
        event(a.at, "arrival", a)
    queue, model_queue, active, records, trace, cache = [], [], set(), {}, [], {}
    model_used, clock = 0, 0.0

    def dispatch(now):
        nonlocal model_used
        while queue and len(active) < n:
            a = queue.pop(0)
            active.add(a.request_id)
            records[a.request_id]["admitted_at"] = now
            model_queue.append((a, 0))
            trace.append(
                {"event": "admit", "at": now, "request_id": a.request_id, "retained_patch_slots": len(active)}
            )
        while model_queue and model_used < model_capacity:
            a, phase = model_queue.pop(0)
            record = records[a.request_id]
            # This model owns only a reusable initial-prefix cache, not private
            # pinned session KV. Tool return reconstructs all uncached history.
            resident = bool(
                a.prefix_identity
                and a.prefix_identity in cache
                and cache[a.prefix_identity][0] >= a.prompt_tokens
                and a.prompt_tokens > 0
            )
            hit_tokens = a.prompt_tokens if resident else 0
            full_prompt = a.prompt_tokens + (a.output_tokens + a.appended_tokens if phase else 0)
            tokens = full_prompt - hit_tokens
            warm = resident
            if resident:
                cache[a.prefix_identity] = (cache[a.prefix_identity][0], now)
            ttft = duration(tokens, prefill_tokens_per_second, "prefill")
            service_duration = finite_real(
                ttft + duration(a.output_tokens, decode_tokens_per_second, "decode"),
                "service duration",
                minimum=0,
            )
            first_token_at = finite_real(now + ttft, "first token time", minimum=0)
            finished_at = finite_real(now + service_duration, "service finish", minimum=0)
            record.setdefault("model_stages", []).append(
                {
                    "phase": phase,
                    "started_at": now,
                    "first_token_at": first_token_at,
                    "finished_at": finished_at,
                    "warm": warm,
                    "prefill_tokens": tokens,
                    "full_prompt_tokens": full_prompt,
                    "cache_hit_tokens": hit_tokens,
                }
            )
            model_used += 1
            trace.append(
                {
                    "event": "model_start",
                    "at": now,
                    "request_id": a.request_id,
                    "phase": phase,
                    "model_slots": model_used,
                    "retained_patch_slots": len(active),
                    "warm": warm,
                }
            )
            event(finished_at, "model_done", (a, phase))

    while event_heap:
        clock, _, _, kind, payload = heapq.heappop(event_heap)
        if kind == "arrival":
            a = payload
            record = {"arrival_at": clock, "status": "queued"}
            records[a.request_id] = record
            if len(active) >= n and len(queue) >= queue_limit:
                record["status"] = "rejected"
                trace.append({"event": "reject", "at": clock, "request_id": a.request_id})
            else:
                queue.append(a)
                trace.append(
                    {"event": "arrival", "at": clock, "request_id": a.request_id, "queue_depth": len(queue)}
                )
        elif kind == "model_done":
            a, phase = payload
            model_used -= 1
            if a.prefix_identity and a.prompt_tokens <= cache_capacity_tokens:
                cache[a.prefix_identity] = (a.prompt_tokens, clock)
                while sum(size for size, _ in cache.values()) > cache_capacity_tokens:
                    victim = min(cache, key=lambda k: (cache[k][1], k))
                    del cache[victim]
                    trace.append({"event": "cache_evict", "at": clock, "prefix_identity": victim})
            if phase == 0 and (a.tool_gap_seconds or a.appended_tokens):
                trace.append(
                    {
                        "event": "tool_idle",
                        "at": clock,
                        "request_id": a.request_id,
                        "retained_patch_slots": len(active),
                    }
                )
                event(clock + a.tool_gap_seconds, "tool_done", a)
            else:
                active.remove(a.request_id)
                records[a.request_id].update(status="completed", completed_at=clock)
                trace.append(
                    {
                        "event": "complete",
                        "at": clock,
                        "request_id": a.request_id,
                        "retained_patch_slots": len(active),
                    }
                )
        else:
            model_queue.append((payload, 1))
        dispatch(clock)
    completed = [r for r in records.values() if r["status"] == "completed"]

    def quantiles(values):
        values = sorted(values)
        return {
            str(p): values[min(len(values) - 1, math.ceil(p * len(values)) - 1)] if values else None
            for p in (0.5, 0.95, 0.99)
        }

    return {
        "evidence": "synthetic open-loop arrival replay",
        "n": n,
        "arrivals": len(arrivals),
        "completed": len(completed),
        "rejected": sum(r["status"] == "rejected" for r in records.values()),
        "queue_seconds": quantiles([r["admitted_at"] - r["arrival_at"] for r in completed]),
        "end_to_end_seconds": quantiles([r["completed_at"] - r["arrival_at"] for r in completed]),
        "mean_retention_seconds": mean([r["completed_at"] - r["admitted_at"] for r in completed])
        if completed
        else None,
        "records": records,
        "trace": trace,
        "cache_policy": "only shared initial prefixes are resident; no private pinned session KV; phase1 prompt=initial prompt+prior output+tool append; reuse only currently resident initial prefix",
        "limitations": "Fixed synthetic token rates; no engine batching, actual KV residency, SLO or coding success measurement.",
    }
