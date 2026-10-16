"""Read bytes only from the current dispatch's immutable offload allowlist."""

import base64
import re

from .artifacts import digest_bytes


def read_context_artifact(artifacts, tenant_id, task_id, accepted_offloads, arguments, *, max_bytes=8192):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 8192:
        raise ValueError("invalid retrieval bound")
    if not isinstance(arguments, dict) or set(arguments) != {"digest", "offset", "limit"}:
        raise ValueError("invalid retrieval arguments")
    digest, offset, limit = (arguments[k] for k in ("digest", "offset", "limit"))
    if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= max_bytes):
        raise ValueError("invalid retrieval range or digest")
    if not isinstance(accepted_offloads, list):
        raise ValueError("invalid accepted offload allowlist")
    matches = []
    for entry in accepted_offloads:
        if not isinstance(entry, dict) or set(entry) != {
            "call_id", "message_index", "block_index", "digest", "size", "encoding", "artifact_ref"
        }:
            raise ValueError("invalid accepted offload descriptor")
        ref = entry["artifact_ref"]
        if (not isinstance(ref, dict) or set(ref) != {
                "tenant_id", "task_id", "digest", "size", "content_type"}
                or ref["tenant_id"] != tenant_id or ref["task_id"] != task_id
                or ref["digest"] != entry["digest"] or type(ref["size"]) is not int
                or ref["size"] != entry["size"]
                or type(entry["size"]) is not int or entry["size"] < 0
                or entry["encoding"] != "utf-8"
                or type(entry["message_index"]) is not int or entry["message_index"] < 0
                or (entry["block_index"] is not None and (
                    type(entry["block_index"]) is not int or entry["block_index"] < 0))
                or not isinstance(entry["call_id"], str) or not entry["call_id"]):
            raise ValueError("invalid scoped offload reference")
        if entry["digest"] == digest:
            matches.append(entry)
    if not matches:
        raise PermissionError("digest is not authorized by current projection")
    if len({entry["size"] for entry in matches}) != 1:
        raise ValueError("inconsistent offload references")
    data = artifacts.get(tenant_id, task_id, digest)
    if len(data) != matches[0]["size"] or digest_bytes(data) != digest:
        raise ValueError("offload artifact integrity failure")
    if offset > len(data):
        raise ValueError("offset exceeds artifact size")
    chunk = data[offset:offset + limit]
    next_offset = offset + len(chunk)
    return {"digest": digest, "offset": offset, "total_size": len(data), "size": len(chunk),
            "next_offset": next_offset, "eof": next_offset == len(data),
            "bytes_base64": base64.b64encode(chunk).decode("ascii")}
