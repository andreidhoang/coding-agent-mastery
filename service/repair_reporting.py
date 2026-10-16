"""Offline maintainer report from public committed repair records only."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .artifacts import LocalArtifacts, digest_bytes
from .execution import tree_digest
from .reporting import write_report


def _public_receipt(artifacts, task, ref):
    """Follow only an explicitly selected, task-scoped public evidence reference."""
    if artifacts is None:
        return None, "unavailable: artifact store was not supplied"
    if not isinstance(ref, dict) or (
        ref.get("tenant_id") != task["tenant_id"] or ref.get("task_id") != task["task_id"]
    ):
        return None, "unavailable: public receipt reference is missing or outside this task"
    try:
        receipt = artifacts.get_json(task["tenant_id"], task["task_id"], ref["digest"])
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be an object")
    except (OSError, ValueError, KeyError, TypeError):
        return None, "unavailable: public receipt bytes could not be read or validated"
    return receipt, "available"


def _candidate(snapshot):
    task = snapshot["task"]
    candidates = snapshot["candidates"]
    head_id = task.get("head_candidate_id")
    if head_id:
        candidate = next((c for c in candidates if c["candidate_id"] == head_id), None)
        return candidate, "current_head"
    workers = [c for c in candidates if c.get("kind") == "worker"]
    return (max(workers, key=lambda c: c.get("accepted_at", 0)) if workers else None), "candidate_only"


def _verification(snapshot, candidate, source, artifacts):
    task, contract = snapshot["task"], snapshot["task"]["contract"]
    result = {"status": "unverified", "verified": False, "receipt": None,
              "evidence_available": False, "cases": [],
              "message": "No exact current-head independent verification receipt."}
    if candidate is None or source != "current_head":
        return result
    failed = task.get("execution_state") == "failed"
    failure = task.get("failure", {})

    def generation_matches(record):
        if record.get("generation") == task.get("generation"):
            return not failed or record.get("outcome") in {"fail", "error"}
        # Terminal failure revokes authority by incrementing the task generation.
        # Display only the non-pass receipt explicitly bound by that transition;
        # never revive a historical passing receipt into current verification.
        return (
            failed and record.get("outcome") in {"fail", "error"}
            and type(failure.get("generation")) is int
            and failure["generation"] + 1 == task.get("generation")
            and record.get("generation") == failure["generation"]
            and isinstance(failure.get("evidence_ref"), dict)
            and record.get("evidence_ref") == failure["evidence_ref"]
        )

    # A worker test or stale passing tree cannot establish current-head verification.
    matches = [v for v in snapshot["verifications"] if (
        v.get("candidate_id") == task.get("head_candidate_id")
        and generation_matches(v)
        and v.get("tenant_id") == task["tenant_id"] and v.get("task_id") == task["task_id"]
        and v.get("contract_digest") == task["contract_digest"]
        and v.get("tree_digest") == candidate.get("tree_digest")
        and v.get("grader_digest") == contract.get("grader_digest")
        and v.get("environment_digest") == contract.get("environment_digest")
        and v.get("authority") == "trusted-control-plane"
    )]
    if not matches:
        return result
    # Equal timestamp precision must not select a passing record over a failure.
    record = max(matches, key=lambda v: (v.get("recorded_at", 0), v.get("outcome") != "pass"))
    result["receipt"] = {k: record.get(k) for k in (
        "verification_id", "generation", "outcome", "tree_digest", "grader_digest", "environment_digest",
        "evidence_ref"
    )}
    result["status"] = record.get("outcome", "error")
    result["verified"] = record.get("outcome") == "pass" and not failed
    result["message"] = "Independent checks " + str(result["status"]) + " for the current head."
    receipt, availability = _public_receipt(artifacts, task, record.get("evidence_ref"))
    result["evidence_availability"] = availability
    if receipt is not None:
        compatible = (
            receipt.get("phase") == "final"
            and all(receipt.get(k) == record.get(k) for k in (
                "tree_digest", "grader_digest", "environment_digest", "outcome"
            ))
            and type(receipt.get("passed")) is bool
            and receipt["passed"] == (record.get("outcome") == "pass")
        )
        if not compatible:
            result.update(status="unverified", verified=False,
                          message="Public evidence conflicts with the current-head receipt.")
        else:
            result["evidence_available"] = True
            # Only the redacted public case projection is rendered; never raw assertions/outputs.
            result["cases"] = [{k: c.get(k) for k in ("id", "passed", "category")}
                               for c in receipt.get("cases", []) if isinstance(c, dict)]
            result["mode"] = receipt.get("mode")
    return result


def _build_report(snapshot, events, artifacts):
    task = snapshot["task"]
    candidate, source = _candidate(snapshot)
    manifest = candidate.get("manifest", {}) if candidate else {}
    valid_tree = bool(candidate) and isinstance(manifest.get("files"), dict) and (
        all(isinstance(p, str) and isinstance(v, str) for p, v in manifest["files"].items())
        and tree_digest(manifest["files"]) == candidate.get("tree_digest") == manifest.get("tree_digest")
    )
    verification = _verification(snapshot, candidate if valid_tree else None, source, artifacts)
    patch = manifest.get("patch")
    patch_available = valid_tree and isinstance(patch, str)
    dispatches = snapshot["dispatches"]
    worker = [d for d in dispatches if d.get("kind") == "run_tests"]
    unknown_reserved = sum(d.get("bound_units", 0) for d in dispatches
                           if d.get("billing_state") != "settled" and d.get("effect_state") == "unknown")
    budget = {**snapshot["budget"], "unknown_reserved": unknown_reserved,
              "unknown_effects": sum(d.get("effect_state") == "unknown" for d in dispatches),
              "other_reserved": max(0, snapshot["budget"]["reserved"] - unknown_reserved),
              "unit_label": "approved accounting units"}
    evidence_kind = snapshot.get("evidence_kind", "runtime_records")
    evidence_label = (
        "Native mock transport" if evidence_kind == "native_mock_transport_supported_repair"
        else "Operator configured provider; inspect actual request receipts"
        if evidence_kind.startswith("operator_configured_provider_repair")
        else "Runtime records; provider evidence is unspecified"
    )
    return {
        "schema": 1, "task_id": task["task_id"], "tenant_id": task["tenant_id"],
        "verified": verification["verified"],
        "issue": (task["contract"].get("requirements") or [""])[0],
        "execution_state": task["execution_state"], "review_state": task["review_state"],
        "model": task["contract"].get("model"), "evidence_kind": evidence_kind,
        "evidence_label": evidence_label, "repair_scope": snapshot.get("repair_scope", "supported repair"),
        "progress": [{"sequence": e.get("sequence"), "kind": e.get("kind", e.get("type", "event"))}
                     for e in events],
        "candidate": {"candidate_id": candidate.get("candidate_id") if candidate else None,
                      "source": source, "tree_digest": candidate.get("tree_digest") if candidate else None,
                      "changed_paths": manifest.get("changed_paths", []),
                      "tree_valid": valid_tree, "patch_available": patch_available,
                      "patch": patch if patch_available else None,
                      "patch_label": "Current head" if source == "current_head" else "Candidate only; unverified"},
        "independent_tests": verification,
        "worker_tests": {"count": len(worker), "succeeded": sum(d.get("effect_state") == "succeeded"
                                                                 for d in worker),
                         "unknown": sum(d.get("effect_state") == "unknown" for d in worker),
                         "limit": task["contract"].get("repair_spec", {}).get("max_worker_tests"),
                         "meaning": "Cumulative test requests across attempts; successful calls are not test passes."},
        "budget": budget,
        "downloads": {"patch": {"file": "change.patch", "available": patch_available,
                                  "sha256": digest_bytes(patch.encode("utf-8")) if patch_available else None,
                                  "bytes": len(patch.encode("utf-8")) if patch_available else 0},
                      "report": "repair.json", "snapshot": "snapshot.json", "trace": "trace.json"},
        "limits": ["Mock transport does not measure actual model capability.",
                   "Independent checks cover the configured supported recipe and environment.",
                   "Human review and human mastery are separate; neither is inferred here."],
    }


def _html(report):
    def text(value):
        return escape(str(value), quote=True)

    tests, candidate, budget = report["independent_tests"], report["candidate"], report["budget"]
    outcome = "Independent checks passed" if tests["verified"] else "Repair remains unverified"
    progress = "".join("<li>" + text(e["kind"]) + "</li>" for e in report["progress"])
    cases = "".join("<li>" + text(c["id"]) + ": " +
                    ("pass" if c["passed"] is True else "fail") + " · " + text(c["category"]) + "</li>"
                    for c in tests["cases"])
    payload = json.dumps(report, ensure_ascii=False).replace("&", "\\u0026").replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    patch_link = ('<a href="change.patch" download>Download change.patch</a>' if candidate["patch_available"]
                  else "Patch download unavailable; change.patch contains no candidate bytes.")
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Repair evidence</title>
<style>body{font:16px/1.55 system-ui,sans-serif;max-width:940px;margin:32px auto;padding:0 24px;color:#182333;
background:#fafbfc}h1{font-size:2rem}h2{margin-top:32px}pre{background:#edf1f5;padding:18px;white-space:pre-wrap;
overflow-wrap:anywhere}a{color:#005b9a}dt{font-weight:600}dd{margin:0 0 12px;overflow-wrap:anywhere}
.notice{padding:16px;background:#e7eef5;border-left:4px solid #365d80}li{overflow-wrap:anywhere}</style></head><body>
<h1>Repair evidence</h1>""" + f"""
<p class="notice">{text(outcome)} · Human review: {text(report['review_state'])}</p>
<p>{text(report['evidence_label'])} · {text(report['model'])}</p>
<h2>Issue</h2><pre>{text(report['issue'])}</pre><p>{text(report['repair_scope'])}</p>
<h2>Progress</h2><p>Execution: {text(report['execution_state'])}</p>
<p>Worker test requests: {report['worker_tests']['count']} across all attempts. Successful tool calls are feedback,
not independent test passes.</p><details><summary>Recorded progress</summary><ol>{progress}</ol></details>
<h2>Changes</h2><p>{text(candidate['patch_label'])}</p>
<dl><dt>Exact candidate tree</dt><dd>{text(candidate['tree_digest'] or 'unavailable')}</dd>
<dt>Changed files</dt><dd>{text(', '.join(candidate['changed_paths']) or 'none available')}</dd></dl>
<pre>{text(candidate['patch'] if candidate['patch_available'] else 'Candidate patch unavailable.')}</pre>
<h2>Independent test summary</h2><p>{text(tests['message'])}</p>
<p>Public receipt details: {text(tests.get('evidence_availability', 'unavailable: no matching receipt'))}</p>
<ul>{cases}</ul><p>Human review: {text(report['review_state'])}. A passing receipt does not record human acceptance.</p>
<h2>Costs and retained reservations</h2><dl><dt>Settled spend</dt><dd>{text(budget['spent'])}</dd>
<dt>Total reserved</dt><dd>{text(budget['reserved'])}</dd>
<dt>Effects still Unknown</dt><dd>{text(budget['unknown_effects'])}</dd>
<dt>Unknown effects, still reserved</dt><dd>{text(budget['unknown_reserved'])}</dd>
<dt>Other reservations</dt><dd>{text(budget['other_reserved'])}</dd>
<dt>Approved limit</dt><dd>{text(budget['limit'])}</dd></dl>
<p>Amounts use {text(budget['unit_label'])}. Reserved amounts are retained, not settled spend.</p>
<h2>Downloads</h2><p>{patch_link} · <a href="repair.json" download>Download report</a> ·
<a href="snapshot.json" download>Download state</a> · <a href="trace.json" download>Download trace</a></p>
<p>This report opens locally and makes no network requests.</p><ul>""" + "".join(
        "<li>" + text(limit) + "</li>" for limit in report["limits"]
    ) + '</ul><script type="application/json" id="repair-data">' + payload + "</script></body></html>"


def write_repair_report(output, snapshot, events, *, artifacts: LocalArtifacts | None = None) -> dict:
    """Write exact stored patch bytes and a detached, network-free public evidence view.

    Independent verification status comes from the exact committed receipt identity;
    missing public artifact bytes are separately marked unavailable. The caller must
    provide an API-visible snapshot, never the supervisor's private recipe inputs.
    """
    # JSON detaches caller-owned data before deriving or returning any projection.
    snapshot, events = json.loads(json.dumps(snapshot)), json.loads(json.dumps(events))
    report = _build_report(snapshot, events, artifacts)
    output = Path(output)
    write_report(output, snapshot, events)
    # The generic trace writer's fixed fixture caption predates this repair path.
    # Relabel this derived output only; preserve its source and fixture behavior.
    trace_path = output / "trace.html"
    trace = trace_path.read_text(encoding="utf-8").replace(
        "Measured event order · scripted fixture · human review separate",
        "Recorded event order · " + escape(report["evidence_label"], quote=True) + " · human review separate",
    )
    trace_path.write_text(trace, encoding="utf-8")
    patch = report["candidate"]["patch"]
    (output / "change.patch").write_bytes(patch.encode("utf-8") if patch is not None else b"")
    (output / "repair.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "repair.html").write_text(_html(report), encoding="utf-8")
    return report
