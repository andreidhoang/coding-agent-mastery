"""Deterministic integration of isolated worker deltas against a pinned source tree."""

from __future__ import annotations

import difflib

from .artifacts import digest_json
from .execution import safe_relative, tree_digest


def _lf_lines(text: str) -> list[str]:
    """Git text patches split LF; Unicode separators and CR are file content."""
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _file_patch(name: str, before: str, after: str) -> str:
    result = []
    for line in difflib.unified_diff(_lf_lines(before), _lf_lines(after),
                                     fromfile="a/" + name, tofile="b/" + name):
        result.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(result)


def candidate_manifest(
    base: dict[str, str],
    candidate: dict[str, str],
    allowed_paths: list[str],
    owner: dict,
    requirements: list[str],
    inputs: list[str] | None = None,
) -> dict:
    allowed = set(allowed_paths)
    changed = sorted(name for name in set(base) | set(candidate) if base.get(name) != candidate.get(name))
    if not set(changed) <= allowed:
        raise PermissionError("candidate changes protected paths")
    for name in changed:
        safe_relative(name)
    patch = "".join(_file_patch(name, base.get(name, ""), candidate.get(name, "")) for name in changed)
    result = {
        "schema": 1,
        "base_revision": tree_digest(base),
        "base_files": base,
        "tree_digest": tree_digest(candidate),
        "tree_format": "sha256-text-tree-v1",
        "files": candidate,
        "changed_paths": changed,
        "patch": patch,
        "requirements": requirements,
        "inputs": inputs or [],
        "owner": owner,
    }
    result["manifest_digest"] = digest_json(result)
    return result


def integrate_candidates(base: dict[str, str], candidates: list[dict]) -> dict[str, str]:
    result = dict(base)
    changed_by: dict[str, str | None] = {}
    for candidate in candidates:
        unsigned = {k: v for k, v in candidate.items() if k != "manifest_digest"}
        if candidate.get("manifest_digest") != digest_json(unsigned):
            raise ValueError("candidate manifest integrity failure")
        if candidate["base_revision"] != tree_digest(base) or candidate["tree_digest"] != tree_digest(
            candidate["files"]
        ):
            raise ValueError("candidate base/tree mismatch")
        expected_changes = {
            p for p in set(base) | set(candidate["files"]) if base.get(p) != candidate["files"].get(p)
        }
        if expected_changes != set(candidate["changed_paths"]):
            raise ValueError("candidate omitted changed paths")
        for path in candidate["changed_paths"]:
            value = candidate["files"].get(path)
            if path in changed_by and changed_by[path] != value:
                raise ValueError(f"integration conflict at {path}")
            changed_by[path] = value
            if value is None:
                result.pop(path, None)
            else:
                result[path] = value
    return result
