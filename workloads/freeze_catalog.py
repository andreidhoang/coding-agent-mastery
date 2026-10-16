"""Authoring-only deterministic freeze. Refuses to overwrite existing lock.

Run once with `python -m workloads.freeze_catalog`. To revise an existing
registry, create a new version/root deliberately; do not unpin it at run time.
This script authors trusted fixtures. It never executes a candidate.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from .registry import ROOT, TARGET_FILES, _canonical, _sha, tree_digest

DEFECTS = {
    "tenant_idempotency": (
        "issue_tracker.py",
        '"SELECT * FROM jobs WHERE tenant=? AND request_key=?", (tenant, request_key)',
        '"SELECT * FROM jobs WHERE request_key=?", (request_key,)',
    ),
    "resume_atomicity": (
        "issue_tracker.py", 'start = job["processed"]', "start = 0",
    ),
    "cancellation": (
        "issue_tracker.py", 'if job["status"] in ("complete", "cancelled"):',
        'if job["status"] == "complete":',
    ),
    "cursor_binding": (
        "issue_tracker.py",
        'if type(version) is not int or type(import_id) is not int or (version, owner, import_id) != (1, tenant, job_id):',
        "if version != 1:",
    ),
    "pagination": (
        "issue_tracker.py", "FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT ?",
        "FROM events WHERE job_id=? AND seq>=? ORDER BY seq LIMIT ?",
    ),
    "sync_compatibility": (
        "client.py",
        'while self.tracker.status(self.tenant, job_id)["status"] not in ("complete", "cancelled"):',
        'if self.tracker.status(self.tenant, job_id)["status"] not in ("complete", "cancelled"):',
    ),
}

DESCRIPTIONS = {
    "tenant_idempotency": "Same tenant/key and canonical CSV rows return one import; changed rows conflict; another tenant may reuse the key.",
    "resume_atomicity": "A bounded batch atomically commits issues, processed checkpoint and event; rollback/reopen/retry neither skips nor repeats committed rows.",
    "cancellation": "Cancellation is terminal for an incomplete import; repeated cancellation and processing preserve progress; completed imports remain complete.",
    "cursor_binding": "Malformed, future-sequence, different-tenant and different-import progress cursors are rejected.",
    "pagination": "Progress pages advance strictly past the previous sequence, contain no repeats and reach an empty tail.",
    "sync_compatibility": "Legacy synchronous clients return their tenant's list of issues after full import completion, including imports requiring multiple batches.",
}

# Plausible partial/incorrect fixes differ from both no-op and reference patch.
INCORRECT_FIXES = {
    "tenant_idempotency": ("issue_tracker.py", 'if previous["payload_hash"] != digest:', "if False:"),
    "resume_atomicity": ("issue_tracker.py", 'start = job["processed"]', 'start = max(0, job["processed"] - 1)'),
    "cancellation": ("issue_tracker.py", 'if job["status"] not in ("complete", "cancelled"):', 'if job["status"] == "queued":'),
    "cursor_binding": ("issue_tracker.py", 'if type(version) is not int or type(import_id) is not int or (version, owner, import_id) != (1, tenant, job_id):', 'if version != 1 or owner != tenant:'),
    "pagination": ("issue_tracker.py", "FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT ?", "FROM events WHERE job_id=? AND seq>(?+1) ORDER BY seq LIMIT ?"),
    "sync_compatibility": ("client.py", "return self.tracker.list_issues(self.tenant)", "return self.tracker.list_issues(self.tenant)[:2]"),
}


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _plant(reference, defects):
    result = dict(reference)
    for requirement in defects:
        name, good, bad = DEFECTS[requirement]
        if result[name].count(good) != 1:
            raise ValueError(f"defect location ambiguous: {requirement}")
        result[name] = result[name].replace(good, bad)
    return result


def freeze():
    if (ROOT / "manifests" / "assets.lock.json").exists():
        raise FileExistsError("frozen registry exists; author a new version instead")
    reference = {name: (ROOT / "oracle" / "reference" / name).read_text() for name in TARGET_FILES}
    keys = tuple(DEFECTS)
    templates = {f"repair_{index + 1}": (key,) for index, key in enumerate(keys)}
    # Each coordinated template touches storage/state AND the sync client.
    pairs = ((0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (0, 1, 5))
    templates.update({f"coordinated_{index + 1}": tuple(keys[position] for position in pair) for index, pair in enumerate(pairs)})
    templates["full_import_contract"] = keys
    metadata = {}
    for baseline_id, requirements in templates.items():
        buggy = _plant(reference, requirements)
        incorrect = dict(reference)
        filename, correct_line, wrong_line = INCORRECT_FIXES[requirements[0]]
        if incorrect[filename].count(correct_line) != 1:
            raise ValueError("ambiguous incorrect control location")
        incorrect[filename] = incorrect[filename].replace(correct_line, wrong_line)
        for directory, sources in ((ROOT / "baseline" / baseline_id, buggy),
                                   (ROOT / "oracle" / "incorrect" / baseline_id, incorrect)):
            directory.mkdir(parents=True, exist_ok=True)
            for name, source in sources.items():
                (directory / name).write_text(source, encoding="utf-8")
        patch = "".join("".join(difflib.unified_diff(buggy[name].splitlines(keepends=True), reference[name].splitlines(keepends=True),
                                                    fromfile=f"a/{name}", tofile=f"b/{name}")) for name in TARGET_FILES)
        patch_path = ROOT / "oracle" / "patches" / f"{baseline_id}.patch"
        patch_path.write_text(patch, encoding="utf-8")
        incorrect_patch = "".join("".join(difflib.unified_diff(buggy[name].splitlines(keepends=True), incorrect[name].splitlines(keepends=True),
                                                              fromfile=f"a/{name}", tofile=f"b/{name}")) for name in TARGET_FILES)
        (ROOT / "oracle" / "patches" / f"{baseline_id}.incorrect.patch").write_text(incorrect_patch, encoding="utf-8")
        metadata[baseline_id] = {"base_digest": tree_digest(ROOT / "baseline" / baseline_id),
                                 "patch_sha256": _sha(patch.encode("utf-8")),
                                 "incorrect_patch_sha256": _sha(incorrect_patch.encode("utf-8")),
                                 "incorrect_tree_digest": tree_digest(ROOT / "oracle" / "incorrect" / baseline_id)}
    grader_hash = _sha((ROOT / "oracle" / "fixtures" / "acceptance.py").read_bytes())
    tasks = []

    def add(task_id, split, tier, baseline_id, variant):
        requirements = templates[baseline_id]
        milestones = (["Repair and regress the stated behavior"] if tier == "T1" else
                      ["Freeze the shared interface and reproduce", "Integrate implementation and client regression checks"] if tier == "T2" else
                      ["Persist resumable submission and batch state", "Integrate terminal cancellation and bound progress cursors", "Preserve sync clients and verify fresh reopen end-to-end"])
        row = {
            "task_id": task_id, "split": split, "tier": tier, "variant": variant,
            "template_group": baseline_id, "baseline_id": baseline_id,
            "baseline_digest": metadata[baseline_id]["base_digest"],
            "reference_patch_sha256": metadata[baseline_id]["patch_sha256"],
            "reference_tree_digest": tree_digest(ROOT / "oracle" / "reference"),
            "incorrect_patch_sha256": metadata[baseline_id]["incorrect_patch_sha256"],
            "incorrect_tree_digest": metadata[baseline_id]["incorrect_tree_digest"],
            "grader_sha256": grader_hash, "requirements": list(requirements),
            "deadline_seconds": {"T1": 900, "T2": 3600, "T3": 10800}[tier],
            "repository": {"family": "synthetic-issue-tracker-v1", "base_commit": None,
                           "identity_kind": "sha256-canonical-file-pairs-v1"},
            "allowed_paths": list(TARGET_FILES), "intentional_added_files": [],
            "provenance": {"author": "Codex AI", "date": "2026-10-08", "data": "synthetic issue labels and IDs only",
                           "kind": "template_variant", "independent_task_claim": False,
                           "known_contamination": "all variants share one published fixture and grader family",
                           "held_out_eligible": False},
            "environment": {"python": ">=3.11", "dependency_lock": "stdlib-only-v1",
                            "network": "disabled", "credentials": "none", "image_digest": None,
                            "architecture": None, "resource_caps": None},
            "model": None, "harness_revision": None, "budget_ceilings": None,
            "live_run_ready": False,
            "visible_spec": {"task_id": task_id, "title": f"{tier} synthetic import contract {variant}",
                             "requirements": [{"id": key, "description": DESCRIPTIONS[key]} for key in requirements],
                             "milestones": milestones, "allowed_paths": list(TARGET_FILES),
                             "misleading_hypothesis": "Skipping duplicate issue inserts alone makes import retries safe; check progress/events separately.",
                             "preserve": "CSV headers issue_id,title; stable tenant-scoped issues; stdlib-only; no network or credentials.",
                             "tier_limitation": "Nominal curriculum tier; task hardness and active long-horizon duration are not established.",
                             "data_label": f"Synthetic {variant}"},
        }
        row["definition_digest"] = _sha(_canonical(row))
        tasks.append(row)

    for index in range(6):
        add(f"calibration-{index + 1:02}", "calibration", "T1", f"repair_{index + 1}", index)
    for index in range(12):
        add(f"diagnostic-t1-{index + 1:02}", "diagnostic", "T1", f"repair_{index % 6 + 1}", 100 + index)
        add(f"diagnostic-t2-{index + 1:02}", "diagnostic", "T2", f"coordinated_{index % 6 + 1}", 200 + index)
        add(f"diagnostic-t3-{index + 1:02}", "diagnostic", "T3", "full_import_contract", 300 + index)
    registry = {"schema_version": 1, "registry_id": "synthetic-issue-tracker-v1-2026-10-08",
                "provenance": "AI-authored synthetic controlled fixture; no public benchmark or independent task-population claim",
                "counts": {"calibration": 6, "diagnostic": 36, "diagnostic_tiers": {"T1": 12, "T2": 12, "T3": 12},
                           "repository_families": 1, "unique_defect_templates": 13},
                "split_note": "Calibration and diagnostic IDs are operationally separate but structurally related; no held-out confirmation set exists.",
                "tasks": sorted(tasks, key=lambda row: row["task_id"])}
    _write_json(ROOT / "manifests" / "tasks.json", registry)
    files = {}
    for folder in ("baseline", "oracle", "manifests"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.name != "assets.lock.json":
                files[str(path.relative_to(ROOT))] = _sha(path.read_bytes())
    _write_json(ROOT / "manifests" / "assets.lock.json",
                {"schema_version": 1, "identity_kind": "sha256-byte-content-v1", "files": files,
                 "authority": "trusted fixture author/verifier; deploy outside candidate write authority"})


if __name__ == "__main__":
    freeze()
