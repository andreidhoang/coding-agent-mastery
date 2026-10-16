"""Independent frozen-contract checks; synthetic transport, no external sockets or payments.

Assertions were derived from provider-qualification-spec-2026-10-11.md before
reading qualification implementation. Repair preparation uses existing public APIs.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import threading
import time

import httpx
import pytest

from service.artifacts import LocalArtifacts, canonical_bytes, digest_bytes, digest_json
from service.billing import ProviderEnvelope
from service.repair import RepairEngine
from service.repair_demo import demo_inputs
from service.repair_provider import ProviderApproval
from service.repair_verification import PythonFunctionRecipe, PythonFunctionVerifier
from service.storage import RuntimeStore

IMAGE = "sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9"
ISSUE = "PRIVATE_QUALIFICATION_ISSUE_48b9"
PRIVATE = "PRIVATE_QUALIFICATION_CASE_a6d2"
AMBIENT = "AMBIENT_SECRET_NOT_A_CREDENTIAL_71ce"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("qualification attempted an external socket")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setenv("NEBIUS_API_KEY", AMBIENT)
    monkeypatch.setenv("OPENAI_API_KEY", AMBIENT)
    monkeypatch.setenv("HTTPS_PROXY", "http://external.invalid:3199")
    monkeypatch.setenv("ALL_PROXY", "http://external.invalid:3199")

    def inspect_only(argv, **kwargs):
        assert argv == ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}} {{.Architecture}} {{.Os}}"]
        return {"exit_code": 0, "reason": "exited", "process_group_retired": True,
                "truncated": False, "output": (IMAGE + " arm64 linux\n").encode()}
    monkeypatch.setattr("service.repair_verification.bounded_process", inspect_only)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected candidate/subprocess execution"))
    monkeypatch.setattr(PythonFunctionVerifier, "verify",
                        lambda *a, **k: pytest.fail("qualification invoked repair verification"))


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "repair"
    artifacts = LocalArtifacts(root / "artifacts")
    private = LocalArtifacts(root / "control-inputs")
    store = RuntimeStore("sqlite:///" + str(root / "authority.sqlite"), artifacts)
    repository, recipe, approval, _ = demo_inputs()
    raw = recipe.as_dict()
    raw["final_cases"].append({"id": PRIVATE, "function": "normalize_slug", "args": [PRIVATE],
                               "kwargs": {}, "expect": {"value": "private-qualification-case-a6d2"}})
    recipe = PythonFunctionRecipe.from_dict(raw)
    raw = approval.as_dict()
    raw["rate_snapshot"].update(rate_id="mock:qualification-nonzero", input_per_million=1000,
                                 output_per_million=2000)
    approval = ProviderApproval.from_dict(raw)
    verifier = PythonFunctionVerifier(IMAGE, recipe=recipe)
    engine = RepairEngine(store, artifacts, root / "workspaces", verifier, private_inputs=private)
    task = engine.submit(repository, recipe, approval, ISSUE, tenant="qualification-test", key="repair-1",
                         budget_units=10000, execution_deadline=time.time() + 7200,
                         review_deadline=time.time() + 14400)
    info = {"schema": 1, "tenant": "qualification-test", "task_id": task["task_id"], "image": IMAGE}
    (root / "repair-task.json").write_text(json.dumps(info))
    store.close()
    return root, info, approval


def module():
    from service import qualification
    return qualification


def freeze(prepared, tmp_path, **updates):
    deadlines = {"execution_deadline": time.time() + 600, "review_deadline": time.time() + 1200}
    deadlines.update(updates)
    output = tmp_path / "qualification"
    result = module().prepare_qualification(output, prepared[0], **deadlines)
    assert isinstance(result, dict)
    return output


def bytes_tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def repair_state(prepared):
    root, info, _ = prepared
    # Existing public reader against a disposable consistent SQLite copy.
    with sqlite3.connect(f"file:{root / 'authority.sqlite'}?mode=ro", uri=True) as source:
        with sqlite3.connect(":memory:") as target:
            source.backup(target)
            return list(target.iterdump())


def ledger(output):
    with sqlite3.connect(f"file:{output / 'authority.sqlite'}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tasks = [dict(x) for x in conn.execute("select * from tasks")]
    assert len(tasks) == 1
    artifacts = LocalArtifacts(output / "artifacts")
    # Read snapshot through existing APIs using a disposable backup, never upstream writer.
    copy_db = output.parent / (output.name + "-read-copy.sqlite")
    with sqlite3.connect(f"file:{output / 'authority.sqlite'}?mode=ro", uri=True) as src:
        with sqlite3.connect(copy_db) as dest:
            src.backup(dest)
    store = RuntimeStore("sqlite:///" + str(copy_db), artifacts)
    try:
        state = store.snapshot(tasks[0]["tenant_id"], tasks[0]["task_id"])
    finally:
        store.close()
        copy_db.unlink()
    return state, artifacts


def artifact(artifacts, ref):
    data = artifacts.get(ref["tenant_id"], ref["task_id"], ref["digest"])
    assert len(data) == ref["size"]
    return data


def pending_flags(report):
    assert report["evidence_kind"] == "offline_mock"
    for key in ("live_observed", "g1_passed", "g2_passed", "execution_authority"):
        assert report[key] is False


def test_two_native_requests_accounting_advisory_handoff_and_upstream_immutable(prepared, tmp_path):
    upstream = bytes_tree(prepared[0]), repair_state(prepared)
    output = freeze(prepared, tmp_path)
    frozen = json.loads((output / "manifest.json").read_bytes())
    assert frozen["provider_approval"] == prepared[2].as_dict()
    bound = ProviderEnvelope(prepared[2].rate_snapshot, prepared[2].model).bound_units
    assert frozen["budget_units"] == 2 * bound > 0
    report = module().run_qualification(output)
    pending_flags(report)
    assert report["passed"] is True
    state, artifacts = ledger(output)
    models = sorted((d for d in state["dispatches"] if d["kind"] == "model.nebius"),
                    key=lambda d: int(d["action_id"].rsplit("-", 1)[1]))
    assert len(models) == 2
    assert all(d["billing_state"] == "settled" and d["actual_units"] > 0 for d in models)
    assert state["budget"]["spent"] == sum(d["actual_units"] for d in models) > 0
    assert state["budget"]["reserved"] == 0
    requests = [artifacts.get_json(state["task"]["tenant_id"], state["task"]["task_id"],
                                   d["input_digest"]) for d in models]
    raw = [json.loads(artifact(artifacts, d["result_ref"])) for d in models]
    first = raw[0]["choices"][0]["message"]
    second_messages = requests[1]["payload"]["messages"]
    assert first in second_messages
    assert any(k not in {"role", "content", "tool_calls"} for k in first)
    read_call = first["tool_calls"][0]
    assert read_call["function"]["name"] == "read_file"
    linked = next(m for m in second_messages if m.get("tool_call_id") == read_call["id"])
    read = json.loads(linked["content"])
    assert read["tool"] == "read_file" and read["ok"] is True
    assert digest_bytes(read["value"]["text"].encode()) == digest_bytes(frozen["fixture"]["text"].encode())
    assert raw[1]["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "finish"
    assert state["task"]["execution_state"] != "review_eligible"
    assert not state["verifications"] and not state["reviews"]
    assert all(s["status"] == "retired" for s in state["sandboxes"])
    report_bytes = bytes_tree(output)
    assert module().run_qualification(output) == report
    assert module().read_qualification_report(output) == report
    assert bytes_tree(output) == report_bytes
    handoff = module().create_qualification_handoff(output, prepared[0])
    assert handoff["execution_authority"] is False
    original = (output / "handoff.json").read_bytes()
    assert module().create_qualification_handoff(output, prepared[0]) == handoff
    assert (output / "handoff.json").read_bytes() == original
    assert (bytes_tree(prepared[0]), repair_state(prepared)) == upstream
    public = b"\n".join(bytes_tree(output).values())
    for private in (ISSUE, PRIVATE, AMBIENT):
        assert private.encode() not in public


@pytest.mark.parametrize("field,value", [("execution_deadline", True), ("review_deadline", False),
                                          ("execution_deadline", float("inf")),
                                          ("review_deadline", float("nan")),
                                          ("execution_deadline", "1800000000"),
                                          ("execution_deadline", 0), ("review_deadline", 1)])
def test_prepare_rejects_bad_deadlines_without_output_or_upstream_write(prepared, tmp_path, field, value):
    before = bytes_tree(prepared[0])
    with pytest.raises((ValueError, TypeError)):
        freeze(prepared, tmp_path, **{field: value})
    assert not (tmp_path / "qualification").exists()
    assert bytes_tree(prepared[0]) == before


def test_manifest_immutable_detached_canonical_and_exact_schema(prepared, tmp_path):
    output = freeze(prepared, tmp_path)
    raw = json.loads((output / "manifest.json").read_bytes())
    manifest = module().QualificationManifest.from_dict(raw)
    expected = copy.deepcopy(raw)
    raw["provider_approval"]["evidence"]["identity"] = "changed"
    detached = manifest.as_dict()
    detached["source_hashes"].clear()
    assert manifest.as_dict() == expected
    assert manifest.digest == digest_json(expected)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        manifest._canonical = b"{}"
    for field in expected:
        invalid = copy.deepcopy(expected)
        del invalid[field]
        with pytest.raises((ValueError, TypeError)):
            module().QualificationManifest.from_dict(invalid)
    for field, value in [("schema", True), ("max_turns", True), ("context_bytes", True),
                         ("budget_units", True), ("mode", "live"), ("unknown", 1)]:
        invalid = copy.deepcopy(expected)
        invalid[field] = value
        with pytest.raises((ValueError, TypeError)):
            module().QualificationManifest.from_dict(invalid)


@pytest.mark.parametrize("edit", ["duplicate", "unknown", "bad_digest", "bad_type"])
def test_manifest_file_corruption_denied_before_dispatch(prepared, tmp_path, edit):
    output = freeze(prepared, tmp_path)
    path = output / "manifest.json"
    raw = json.loads(path.read_bytes())
    if edit == "duplicate":
        path.write_text('{"schema":1,' + path.read_text()[1:])
    else:
        if edit == "unknown":
            raw["secret"] = AMBIENT
        elif edit == "bad_digest":
            raw["source_hashes"][next(iter(raw["source_hashes"]))] = "x" * 64
        else:
            raw["budget_units"] = True
        path.write_text(json.dumps(raw))
    with pytest.raises((ValueError, TypeError)):
        module().run_qualification(output)
    assert not (output / "started.json").exists()


@pytest.mark.parametrize("where", ["same", "child", "ancestor"])
def test_output_overlap_and_missing_input_never_bootstraps(prepared, tmp_path, where):
    root = prepared[0]
    output = {"same": root, "child": root / "qualification", "ancestor": tmp_path}[where]
    before = bytes_tree(root)
    with pytest.raises((ValueError, FileExistsError)):
        module().prepare_qualification(output, root, execution_deadline=time.time() + 100,
                                       review_deadline=time.time() + 200)
    assert bytes_tree(root) == before
    missing = tmp_path / "missing"
    with pytest.raises((ValueError, FileNotFoundError)):
        module().prepare_qualification(tmp_path / "missing-q", missing,
                                       execution_deadline=time.time() + 100, review_deadline=time.time() + 200)
    assert not missing.exists()


@pytest.mark.parametrize("drift", ["add", "remove", "modify"])
def test_complete_running_package_source_set_drift_denied(prepared, tmp_path, monkeypatch, drift):
    output = freeze(prepared, tmp_path)
    original = module()._source_hashes()
    changed = dict(original)
    path = next(iter(changed))
    if drift == "add":
        changed["sub/extra.py"] = "0" * 64
    elif drift == "remove":
        del changed[path]
    else:
        changed[path] = "0" * 64
    monkeypatch.setattr(module(), "_source_hashes", lambda: changed)
    with pytest.raises(ValueError):
        module().run_qualification(output)
    assert not (output / "started.json").exists()


def test_interrupted_marker_never_restarts(prepared, tmp_path, monkeypatch):
    output = freeze(prepared, tmp_path)
    (output / "started.json").write_text('{"interrupted":true}')
    monkeypatch.setattr(module(), "_mock_transport", lambda *a: pytest.fail("interrupted run resent"))
    with pytest.raises((ValueError, RuntimeError, FileExistsError)):
        module().run_qualification(output)
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        module().create_qualification_handoff(output, prepared[0])


@pytest.mark.parametrize("state_change", ["claim", "cancel", "image", "private_bytes"])
def test_bound_repair_start_cancel_image_private_drift_blocks_handoff(prepared, tmp_path, state_change):
    output = freeze(prepared, tmp_path)
    assert module().run_qualification(output)["passed"]
    root, info, _ = prepared
    if state_change in {"claim", "cancel"}:
        store = RuntimeStore("sqlite:///" + str(root / "authority.sqlite"), LocalArtifacts(root / "artifacts"))
        try:
            if state_change == "claim":
                store.claim(info["tenant"], info["task_id"], "repair", "started", 100, 60)
            else:
                store.cancel(info["tenant"], info["task_id"], "canceled")
        finally:
            store.close()
    elif state_change == "image":
        info = dict(info, image="sha256:" + "0" * 64)
        (root / "repair-task.json").write_text(json.dumps(info))
    else:
        inputs = next(p for p in (root / "control-inputs").rglob("*") if p.is_file())
        inputs.write_bytes(inputs.read_bytes() + b" ")
    before = bytes_tree(root)
    with pytest.raises((ValueError, RuntimeError, AssertionError)):
        module().create_qualification_handoff(output, root)
    assert not (output / "handoff.json").exists()
    assert bytes_tree(root) == before


@pytest.mark.parametrize("fault", ["timeout", "bad_usage", "wrong_model", "malformed_tools", "bad_native"])
def test_failed_native_probe_retains_billing_receipt_and_never_resends(prepared, tmp_path, monkeypatch, fault):
    output = freeze(prepared, tmp_path)
    requests, response_bytes = [], []
    original = module()._mock_transport

    def factory(approval):
        good = original(approval)
        def handler(request):
            requests.append(request)
            if fault == "timeout":
                raise httpx.ReadTimeout("SECRET_EXCEPTION_OMIT_4e11", request=request)
            response = good(request)
            body = response.read()
            raw = json.loads(body)
            if fault == "bad_usage":
                raw["usage"]["prompt_tokens"] = True
            elif fault == "wrong_model":
                raw["model"] = "nvidia/other-model"
            elif fault == "malformed_tools":
                raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"path":true}'
            elif fault == "bad_native":
                raw["choices"][0]["message"]["role"] = "user"
            body = json.dumps(raw).encode()
            response_bytes.append(body)
            return httpx.Response(200, content=body)
        return handler

    monkeypatch.setattr(module(), "_mock_transport", factory)
    report = module().run_qualification(output)
    pending_flags(report)
    assert report["passed"] is False
    assert len(requests) == 1
    state, artifacts = ledger(output)
    models = sorted((d for d in state["dispatches"] if d["kind"] == "model.nebius"),
                    key=lambda d: int(d["action_id"].rsplit("-", 1)[1]))
    assert len(models) == 1
    dispatch = models[0]
    assert all(s["status"] == "retired" for s in state["sandboxes"])
    if fault in {"timeout", "bad_usage", "wrong_model"}:
        assert dispatch["billing_state"] == "liability_unknown"
        assert dispatch["actual_units"] is None
        assert state["budget"]["reserved"] == dispatch["bound_units"] > 0
        assert state["budget"]["spent"] == 0
    else:
        assert dispatch["billing_state"] == "settled" and dispatch["actual_units"] > 0
        assert state["budget"]["spent"] == dispatch["actual_units"]
    if fault == "timeout":
        assert dispatch["effect_state"] == "unknown"
    else:
        assert artifact(artifacts, dispatch["result_ref"]) == response_bytes[0]
    before = bytes_tree(output)
    assert module().run_qualification(output) == report
    assert module().read_qualification_report(output) == report
    assert len(requests) == 1 and bytes_tree(output) == before
    with pytest.raises((ValueError, RuntimeError)):
        module().create_qualification_handoff(output, prepared[0])
    assert not (output / "handoff.json").exists()
    assert b"SECRET_EXCEPTION_OMIT_4e11" not in b"\n".join(bytes_tree(output).values())


def test_concurrent_run_admits_exactly_one_two_request_probe(prepared, tmp_path, monkeypatch):
    output = freeze(prepared, tmp_path)
    original = module()._mock_transport
    entered, release = threading.Event(), threading.Event()
    calls = []
    def factory(approval):
        good = original(approval)
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                entered.set()
                assert release.wait(10)
            return good(request)
        return handler
    monkeypatch.setattr(module(), "_mock_transport", factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(module().run_qualification, output)
        assert entered.wait(10)
        second = pool.submit(module().run_qualification, output)
        try:
            with pytest.raises((ValueError, RuntimeError, FileExistsError)):
                second.result(timeout=10)
        finally:
            release.set()
        assert first.result(timeout=20)["passed"] is True
    assert len(calls) == 2
    state, _ = ledger(output)
    assert len(state["attempts"]) == 1
    assert len([d for d in state["dispatches"] if d["kind"] == "model.nebius"]) == 2


@pytest.mark.parametrize("damage", ["raw_missing", "raw_corrupt", "report_summary", "report_ref_size", "source_after_pass"])
def test_evidence_corruption_or_forged_summary_blocks_report_and_handoff(prepared, tmp_path, monkeypatch, damage):
    output = freeze(prepared, tmp_path)
    module().run_qualification(output)
    if damage.startswith("raw"):
        state, artifacts = ledger(output)
        ref = next(d["result_ref"] for d in state["dispatches"] if d["kind"] == "model.nebius")
        path = artifacts.root / ref["tenant_id"] / ref["task_id"] / ref["digest"]
        if damage == "raw_missing":
            path.unlink()
        else:
            path.write_bytes(b"forged raw response")
    elif damage == "source_after_pass":
        source = dict(module()._source_hashes())
        source[next(iter(source))] = "0" * 64
        monkeypatch.setattr(module(), "_source_hashes", lambda: source)
    else:
        path = output / "report.json"
        index = json.loads(path.read_bytes())
        if damage == "report_ref_size":
            index["report_ref"]["size"] += 1
        else:
            index["passed"] = False
        path.write_bytes(canonical_bytes(index))
    before = bytes_tree(output)
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        module().read_qualification_report(output)
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        module().create_qualification_handoff(output, prepared[0])
    assert bytes_tree(output) == before
    assert not (output / "handoff.json").exists()


def test_running_package_source_hashes_match_complete_independent_enumeration():
    root = Path(module().__file__).resolve().parent
    expected = {path.relative_to(root).as_posix(): digest_bytes(path.read_bytes())
                for path in root.rglob("*.py") if path.is_file()}
    assert module()._source_hashes() == expected
    assert any("/" in name for name in expected), "recursive subpackage evidence required"


def test_operator_evidence_still_uses_only_internal_mock_and_ignores_ambient_key(tmp_path, monkeypatch):
    original_inputs = demo_inputs
    def operator_inputs():
        repo, recipe, approval, issue = original_inputs()
        data = approval.as_dict()
        data["evidence"] = {"kind": "operator-verified", "identity": "operator:synthetic-test-only"}
        return repo, recipe, ProviderApproval.from_dict(data), issue
    monkeypatch.setitem(globals(), "demo_inputs", operator_inputs)
    prepared_repair = prepared.__wrapped__(tmp_path)
    output = freeze(prepared_repair, tmp_path)
    original = module()._mock_transport
    sent = []
    def transport(approval):
        good = original(approval)
        def handler(request):
            assert request.headers["authorization"] != "Bearer " + AMBIENT
            assert str(request.url) == approval.as_dict()["endpoint"] + "chat/completions"
            sent.append(request)
            return good(request)
        return handler
    monkeypatch.setattr(module(), "_mock_transport", transport)
    report = module().run_qualification(output)
    assert report["passed"] and len(sent) == 2
    assert report["supplied_evidence"] == prepared_repair[2].as_dict()["evidence"]
    pending_flags(report)
    with pytest.raises(TypeError):
        module().run_qualification(output, enable_network=True)
    with httpx.Client(trust_env=False) as external_client:
        with pytest.raises(TypeError):
            module().run_qualification(output, client=external_client)


@pytest.mark.parametrize("damage", ["contract_model", "contract_rate", "node_graph", "missing_database"])
def test_invalid_prepared_repair_refused_before_new_output(prepared, tmp_path, damage):
    root = prepared[0]
    if damage == "missing_database":
        (root / "authority.sqlite").unlink()
    else:
        table = "nodes" if damage == "node_graph" else "tasks"
        with sqlite3.connect(root / "authority.sqlite") as conn:
            conn.create_function("cam_writer_schema", 0, lambda: 2)
            identity, blob = conn.execute(f"select id,data from {table}").fetchone()
            data = json.loads(blob)
            if damage == "node_graph":
                data["dependencies"] = ["unowned-node"]
            elif damage == "contract_model":
                data["contract"]["model"] = "nvidia/different-approved-model"
            else:
                data["contract"]["rate_snapshot"]["input_per_million"] += 1
            conn.execute(f"update {table} set data=? where id=?", (json.dumps(data), identity))
    before = bytes_tree(root)
    with pytest.raises((ValueError, FileNotFoundError)):
        freeze(prepared, tmp_path)
    assert not (tmp_path / "qualification").exists()
    assert bytes_tree(root) == before


@pytest.mark.parametrize("change", ["deadline", "repair_transplant"])
def test_canonical_rehashed_manifest_report_cannot_rebind_a_valid_probe(prepared, tmp_path, change):
    """Rehashing valid JSON is stronger than corrupting bytes: durable contract must bind it."""
    output = freeze(prepared, tmp_path)
    assert module().run_qualification(output)["passed"]
    manifest = json.loads((output / "manifest.json").read_bytes())
    repair_target = prepared[0]
    if change == "deadline":
        manifest["execution_deadline"] += 1
    else:
        import shutil
        repair_target = tmp_path / "transplant-repair"
        shutil.copytree(prepared[0], repair_target)
        manifest["repair_binding"]["repair_output"] = str(repair_target.resolve())
    new_manifest = module().QualificationManifest.from_dict(manifest)
    (output / "manifest.json").write_bytes(canonical_bytes(manifest))
    (output / "started.json").write_bytes(canonical_bytes({"schema": 1, "manifest_digest": new_manifest.digest}))
    index = json.loads((output / "report.json").read_bytes())
    artifacts = LocalArtifacts(output / "artifacts")
    old_ref = index["report_ref"]
    bundle = json.loads(artifact(artifacts, old_ref))
    bundle["manifest_digest"] = new_manifest.digest
    index["manifest_digest"] = new_manifest.digest
    index["report_ref"] = artifacts.put_json(old_ref["tenant_id"], old_ref["task_id"], bundle)
    (output / "report.json").write_bytes(canonical_bytes(index))
    (output / "handoff.json").unlink(missing_ok=True)
    before = bytes_tree(output)
    with pytest.raises((ValueError, RuntimeError)):
        module().read_qualification_report(output)
    with pytest.raises((ValueError, RuntimeError)):
        module().create_qualification_handoff(output, repair_target)
    assert bytes_tree(output) == before
    assert not (output / "handoff.json").exists()
