"""Offline native evidence bound to one prepared repair; never execution authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import httpx

from .artifacts import LocalArtifacts, canonical_bytes, digest_bytes, digest_json
from .billing import ProviderEnvelope
from .contracts import digest, identity, parse_json, strict_int, timestamp, validate_contract
from .execution import Workspace, safe_relative
from .harness import Harness
from .providers import decode_provider_payload, parse_nebius_response, parse_nebius_usage
from .repair import RepairEngine, committed_repair_events
from .repair_provider import ProviderApproval, _mock_client
from .repair_verification import PythonFunctionRecipe, PythonFunctionVerifier
from .repositories import FrozenRepository
from .storage import RuntimeStore

MODE = "offline_mock"
PROBE_REVISION = "native-read-finish-v1"
FIXTURE = {"path": "qualification.txt", "text": "Owned offline qualification fixture.\n"}
TENANT = "qualification"
BINDING_FIELDS = {
    "repair_output", "tenant", "task_id", "service_incarnation", "generation", "contract_digest",
    "private_input_digest", "repository_digest", "recipe_digest", "provider_digest", "image",
    "environment_digest", "snapshot_digest", "frontier_digest",
}
FLAGS = {"evidence_kind": MODE, "live_observed": False, "g1_passed": False,
         "g2_passed": False, "execution_authority": False}


def _read_json(path, *, canonical=False, bound=8 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe qualification input")
    with path.open("rb") as stream:
        raw = stream.read(bound + 1)
    if len(raw) > bound:
        raise ValueError("qualification input exceeds bound")
    value = parse_json(raw)
    if canonical and canonical_bytes(value) != raw:
        raise ValueError("noncanonical qualification bytes")
    return value


def _publish(path, value, *, converge=False):
    """Durable no-overwrite publication, including concurrent callers."""
    path = Path(path)
    raw = canonical_bytes(value)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not converge or path.is_symlink() or path.read_bytes() != raw:
                raise ValueError("qualification index already exists") from None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)


def _source_hashes():
    root = Path(__file__).resolve().parent
    files = {}
    for path in sorted(root.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe service source")
        files[path.relative_to(root).as_posix()] = digest_bytes(path.read_bytes())
    if not files:
        raise ValueError("missing service sources")
    return files


@dataclass(frozen=True, init=False)
class QualificationManifest:
    _canonical: bytes
    FIELDS = {"schema", "mode", "probe_revision", "fixture", "provider_approval", "source_hashes",
              "repair_binding", "execution_deadline", "review_deadline", "max_turns", "context_bytes",
              "budget_units"}

    def __init__(self, *args, **kwargs):
        raise TypeError("construct qualification manifest using from_dict")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != cls.FIELDS:
            raise ValueError("exact qualification manifest fields required")
        value = parse_json(canonical_bytes(value))
        strict_int(value["schema"], "manifest schema", 1, 1)
        if value["mode"] != MODE or value["probe_revision"] != PROBE_REVISION or value["fixture"] != FIXTURE:
            raise ValueError("unsupported qualification probe")
        strict_int(value["max_turns"], "max_turns", 2, 2)
        strict_int(value["context_bytes"], "context_bytes", 131072, 131072)
        approval = ProviderApproval.from_dict(value["provider_approval"])
        bound = ProviderEnvelope(approval.rate_snapshot, approval.model).bound_units
        strict_int(bound * 2, "two-envelope budget")
        strict_int(value["budget_units"], "budget_units", bound * 2, bound * 2)
        for name in ("execution_deadline", "review_deadline"):
            if type(value[name]) not in (float, int):
                raise ValueError("explicit numeric deadline required")
            timestamp(value[name], name)
        if value["execution_deadline"] >= value["review_deadline"]:
            raise ValueError("strictly ordered deadlines required")
        sources = value["source_hashes"]
        if not isinstance(sources, dict) or not sources:
            raise ValueError("complete service source hashes required")
        for name, sha in sources.items():
            if safe_relative(name) != name or not name.endswith(".py"):
                raise ValueError("invalid service source path")
            digest(sha)
        binding = value["repair_binding"]
        if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS:
            raise ValueError("exact repair binding required")
        for name in ("tenant", "task_id", "service_incarnation"):
            identity(binding[name])
        strict_int(binding["generation"], "repair generation", 1, 1)
        for name in BINDING_FIELDS - {"repair_output", "tenant", "task_id", "service_incarnation", "generation", "image"}:
            digest(binding[name])
        if (not isinstance(binding["repair_output"], str)
                or str(Path(binding["repair_output"]).resolve()) != binding["repair_output"]):
            raise ValueError("canonical repair locator required")
        image = binding["image"]
        if not isinstance(image, str) or not image.startswith("sha256:"):
            raise ValueError("immutable image binding required")
        digest(image[7:])
        if binding["provider_digest"] != approval.digest:
            raise ValueError("approval binding mismatch")
        result = object.__new__(cls)
        object.__setattr__(result, "_canonical", canonical_bytes(value))
        return result

    def as_dict(self):
        return json.loads(self._canonical)

    @property
    def digest(self):
        return digest_bytes(self._canonical)


def _existing_root(output):
    path = Path(output).resolve()
    if not path.is_dir():
        raise ValueError("existing control-plane root required")
    return path


def _artifacts(root, name="artifacts"):
    path = root / name
    if path.is_symlink() or not path.is_dir():
        raise ValueError("existing artifact root required")
    return LocalArtifacts(path)


@contextmanager
def _snapshot_store(root, artifacts):
    """Read original SQLite with WAL-aware backup; only the disposable copy bootstraps."""
    database = root / "authority.sqlite"
    if database.is_symlink() or not database.is_file():
        raise ValueError("existing authority database required")
    with tempfile.TemporaryDirectory(prefix="qualification-snapshot-") as temporary:
        copy = Path(temporary) / "authority.sqlite"
        source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(copy)
        try:
            source.execute("BEGIN")
            source.execute("SELECT count(*) FROM sqlite_master").fetchone()
            source.backup(target)
        finally:
            target.close()
            source.close()
        store = RuntimeStore("sqlite:///" + str(copy), artifacts)
        try:
            yield store
        finally:
            store.close()


def _repair_binding(output):
    root = _existing_root(output)
    info = _read_json(root / "repair-task.json", bound=65536)
    if (not isinstance(info, dict) or set(info) != {"schema", "tenant", "task_id", "image"}
            or type(info["schema"]) is not int or info["schema"] != 1):
        raise ValueError("invalid prepared repair identity")
    identity(info["tenant"])
    identity(info["task_id"])
    artifacts, private = _artifacts(root), _artifacts(root, "control-inputs")
    with _snapshot_store(root, artifacts) as store:
        snapshot = store.snapshot(info["tenant"], info["task_id"])
        task, nodes = snapshot["task"], snapshot["nodes"]
        if (task["generation"] != 1 or task["execution_state"] != "running" or task["review_state"] != "none"
                or task["cancel_requested_at"] is not None or task["authority_revoked_at"] is not None
                or snapshot["quarantined"] or len(nodes) != 1):
            raise ValueError("repair is not a supported unstarted preparation")
        node = nodes[0]
        if (node["node_id"] != "repair" or node["status"] != "pending" or node["node_epoch"] != 0
                or node["dependencies"] != [] or node["attempt_id"] is not None or node["candidate_id"] is not None
                or any(snapshot[name] for name in ("attempts", "dispatches", "sandboxes", "candidates",
                                                 "checkpoints", "verifications", "reviews"))):
            raise ValueError("repair has started or its graph drifted")
        contract = validate_contract(task["contract"])
        if digest_json(contract) != task["contract_digest"] or "repair_spec" not in contract:
            raise ValueError("repair contract integrity failure")
        spec = contract["repair_spec"]
        raw_bytes = private.get(info["tenant"], info["task_id"], spec["input_digest"])
        inputs = parse_json(raw_bytes)
        if canonical_bytes(inputs) != raw_bytes or not isinstance(inputs, dict) or set(inputs) != {
                "schema", "repository", "recipe", "provider", "issue"} or type(inputs["schema"]) is not int or inputs["schema"] != 1:
            raise ValueError("invalid private repair input")
        repo = FrozenRepository.from_dict(inputs["repository"])
        recipe = PythonFunctionRecipe.from_dict(inputs["recipe"])
        approval = ProviderApproval.from_dict(inputs["provider"])
        if not isinstance(inputs["issue"], str) or not inputs["issue"].strip() or len(inputs["issue"]) > 8192:
            raise ValueError("invalid private issue")
        RepairEngine._validate_source(dict(repo.files), recipe)
        verifier = PythonFunctionVerifier(info["image"], recipe=recipe)
        if (verifier.image != info["image"] or repo.manifest_digest != spec["repository_digest"]
                or recipe.grader_digest != spec["recipe_digest"] or approval.digest != spec["provider_digest"]
                or repo.tree_digest != contract["base_revision"] or repo.repo_id != contract["repo_id"]
                or recipe.grader_digest != contract["grader_digest"] or verifier.environment_for(recipe) != contract["environment_digest"]
                or approval.model != contract["model"] or approval.rate_snapshot != contract["rate_snapshot"]
                or set(recipe.as_dict()["source_paths"]) != set(repo.files)
                or node["allowed_paths"] != list(repo.allowed_paths)):
            raise ValueError("frozen repair configuration drift")
        # Reconstruct all public requirements without copying them into qualification evidence.
        public = recipe.public_description()
        metadata = {k: v for k, v in public.items() if k != "worker_cases"}
        expected = [inputs["issue"], "Supported repository source paths: " + ", ".join(sorted(repo.files)),
                    "Public function interface: " + canonical_bytes(metadata).decode()] + [
                    "Public test case: " + canonical_bytes(case).decode() for case in public["worker_cases"]]
        if contract["requirements"] != expected:
            raise ValueError("prepared public requirements drift")
        committed_repair_events(store, info["tenant"], info["task_id"], snapshot)
        binding = {"repair_output": str(root), "tenant": info["tenant"], "task_id": info["task_id"],
                   "service_incarnation": snapshot["frontier"]["service_incarnation"], "generation": 1,
                   "contract_digest": task["contract_digest"], "private_input_digest": spec["input_digest"],
                   "repository_digest": repo.manifest_digest, "recipe_digest": recipe.grader_digest,
                   "provider_digest": approval.digest, "image": verifier.image,
                   "environment_digest": contract["environment_digest"], "snapshot_digest": digest_json(snapshot),
                   "frontier_digest": digest_json(snapshot["frontier"])}
        return binding, approval


def _manifest(root):
    return QualificationManifest.from_dict(_read_json(root / "manifest.json", canonical=True))


def _check_sources(manifest):
    if _source_hashes() != manifest.as_dict()["source_hashes"]:
        raise ValueError("complete service source identity drift")


def prepare_qualification(output, repair_output, *, execution_deadline, review_deadline):
    root, repair = Path(output).resolve(), _existing_root(repair_output)
    if root == repair or root.is_relative_to(repair) or repair.is_relative_to(root):
        raise ValueError("qualification and repair roots overlap")
    binding, approval = _repair_binding(repair)
    value = {"schema": 1, "mode": MODE, "probe_revision": PROBE_REVISION, "fixture": FIXTURE,
             "provider_approval": approval.as_dict(), "source_hashes": _source_hashes(), "repair_binding": binding,
             "execution_deadline": execution_deadline, "review_deadline": review_deadline,
             "max_turns": 2, "context_bytes": 131072,
             "budget_units": 2 * ProviderEnvelope(approval.rate_snapshot, approval.model).bound_units}
    manifest = QualificationManifest.from_dict(value)
    if timestamp(execution_deadline, "execution_deadline") <= time.time():
        raise ValueError("qualification execution deadline elapsed")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    _publish(root / "manifest.json", manifest.as_dict())
    fixture = root / "fixture"
    fixture.mkdir(mode=0o700)
    with (fixture / FIXTURE["path"]).open("xb") as stream:
        stream.write(FIXTURE["text"].encode())
    return {**FLAGS, "prepared": True, "manifest_digest": manifest.digest, "output": str(root),
            "supplied_evidence": approval.as_dict()["evidence"]}


def _mock_transport(approval):
    def reply(request):
        payload = parse_json(request.content)
        turn = sum(message["role"] == "assistant" for message in payload["messages"])
        if turn not in (0, 1):
            raise ValueError("fixed qualification turn bound")
        name = "read_file" if turn == 0 else "finish"
        args = {"path": FIXTURE["path"]} if turn == 0 else {"summary": "Offline fixture read; completion proposal only"}
        return httpx.Response(200, json={
            "id": f"qualification-response-{turn}", "object": "chat.completion", "model": approval.model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "reasoning_content": "opaque offline fixture continuation",
                "qualification_opaque": {"revision": PROBE_REVISION, "turn": turn},
                "tool_calls": [{"id": f"qualification-call-{turn}", "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args)}}],
            }}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    return reply


def _fixture_valid(root):
    path = root / "fixture" / FIXTURE["path"]
    return (not path.is_symlink() and path.is_file() and path.read_bytes() == FIXTURE["text"].encode()
            and sorted(p.name for p in path.parent.iterdir()) == [FIXTURE["path"]])


def _ref(artifacts, task_id, sha, content_type="application/json"):
    raw = artifacts.get(TENANT, task_id, sha)
    return {"tenant_id": TENANT, "task_id": task_id, "digest": sha, "size": len(raw), "content_type": content_type}


def _read_ref(artifacts, tenant, task_id, ref):
    if not isinstance(ref, dict) or set(ref) != {"tenant_id", "task_id", "digest", "size", "content_type"}:
        raise ValueError("exact artifact reference required")
    if ref["tenant_id"] != tenant or ref["task_id"] != task_id:
        raise ValueError("artifact scope mismatch")
    strict_int(ref["size"], "artifact size", 0, artifacts.max_bytes)
    if not isinstance(ref["content_type"], str):
        raise ValueError("artifact content type required")
    raw = artifacts.get(tenant, task_id, ref["digest"])
    if len(raw) != ref["size"]:
        raise ValueError("artifact size mismatch")
    return raw


def _linked_refs(artifacts, tenant, task_id, value):
    if isinstance(value, dict):
        if "digest" in value and ("tenant_id" in value or "content_type" in value):
            _read_ref(artifacts, tenant, task_id, value)
        else:
            for child in value.values():
                _linked_refs(artifacts, tenant, task_id, child)
    elif isinstance(value, list):
        for child in value:
            _linked_refs(artifacts, tenant, task_id, child)


def _probe_contract(manifest):
    """One exact supported contract binds durable dispatch authority to frozen inputs."""
    data = manifest.as_dict()
    approval = ProviderApproval.from_dict(data["provider_approval"])
    return validate_contract({
        "schema": 1, "repo_id": "qualification-owned-fixture", "base_revision": digest_json(FIXTURE),
        "requirements": ["Read qualification.txt, then propose finish; offline mechanics only",
                         "Frozen qualification manifest SHA-256: " + manifest.digest],
        "capabilities": ["read_file", "finish"], "max_nodes": 1, "max_attempts": 1,
        "profile": "production", "patch_slot_limit": 1, "budget_units": data["budget_units"],
        "execution_deadline": data["execution_deadline"], "review_deadline": data["review_deadline"],
        "model": approval.model, "rate_snapshot": approval.rate_snapshot,
        "grader_digest": digest_json("qualification-no-verifier-v1"),
        "environment_digest": digest_json("qualification-synchronous-text-only-v1"),
    })


def _expected_native_request(approval, contract, messages):
    # Reuse the supported adapter serializer with a disabled, exclusively mock client.
    def never_send(request):
        raise AssertionError("evidence reconstruction cannot dispatch")
    with httpx.Client(transport=httpx.MockTransport(never_send), trust_env=False, follow_redirects=False) as client:
        adapter = approval.build_adapter("qualification-synthetic-key", enable_network=False, client=client)
        payload = adapter.build_request(messages, "Follow only the frozen task constraints: " + str(contract["requirements"]),
                                        approval.rate_snapshot["max_output_tokens"])
    return {"provider": "nebius", "protocol": "chat_completions", "endpoint": approval.as_dict()["endpoint"],
            "payload": payload}


def _derive_pass(manifest, bundle, artifacts, root):
    """Reconstruct qualification from receipts and native history, never the summary flag."""
    snapshot = bundle["snapshot"]
    task = snapshot["task"]
    task_id = task["task_id"]
    expected_contract = _probe_contract(manifest)
    if (task["tenant_id"] != TENANT or task["generation"] != 1
            or task["contract"] != expected_contract or task["contract_digest"] != digest_json(expected_contract)
            or snapshot["budget"]["limit"] != expected_contract["budget_units"]):
        raise ValueError("durable probe contract differs from frozen qualification manifest")
    _linked_refs(artifacts, TENANT, task_id, bundle)
    approval = ProviderApproval.from_dict(manifest.as_dict()["provider_approval"])
    envelope = ProviderEnvelope(approval.rate_snapshot, approval.model)
    native = bundle["native"]
    if bundle["error_category"] is not None or len(native) != 2 or not _fixture_valid(root):
        return False
    model_dispatches = [d for d in snapshot["dispatches"] if d["kind"] == "model.nebius"]
    tools = [d for d in snapshot["dispatches"] if d["kind"] != "model.nebius"]
    if (len(model_dispatches) != 2 or sorted(d["kind"] for d in tools) != ["finish", "read_file"]
            or task["execution_state"] != "running" or task["review_state"] != "none"
            or task["cancel_requested_at"] is not None or task["authority_revoked_at"] is not None
            or len(snapshot["nodes"]) != 1 or len(snapshot["attempts"]) != 1 or len(snapshot["sandboxes"]) != 1
            or snapshot["sandboxes"][0]["status"] != "retired"
            or any(snapshot[k] for k in ("candidates", "verifications", "reviews"))
            or any(d["effect_state"] != "succeeded" or d["billing_state"] != "settled" for d in snapshot["dispatches"])):
        return False
    node, attempt, sandbox = snapshot["nodes"][0], snapshot["attempts"][0], snapshot["sandboxes"][0]
    owner = attempt["owner"]
    if (set(node) != {"node_id", "dependencies", "role", "allowed_paths", "generation", "node_epoch",
                      "status", "attempt_id", "candidate_id"}
            or node != {"node_id": "probe", "dependencies": [], "role": "patch", "allowed_paths": [],
                        "generation": 1, "node_epoch": 1, "status": "running",
                        "attempt_id": attempt["attempt_id"], "candidate_id": None}
            or owner != {"service_incarnation": snapshot["frontier"]["service_incarnation"],
                         "tenant_id": TENANT, "task_id": task_id, "generation": 1, "node_id": "probe",
                         "node_epoch": 1, "attempt_id": attempt["attempt_id"]}
            or attempt["status"] != "retired" or sandbox["attempt_id"] != attempt["attempt_id"]
            or sandbox["sandbox_id"] != attempt["sandbox_id"]
            or any(d["owner"] != owner or d["attempt_id"] != attempt["attempt_id"] for d in snapshot["dispatches"])
            or any(c["owner"] != owner or c["contract"] != expected_contract for c in snapshot["checkpoints"])):
        return False
    retirement = parse_json(_read_ref(artifacts, TENANT, task_id, sandbox["retirement_evidence"]))
    if retirement != {"schema": 1, "kind": "synchronous-offline-probe-retirement",
                       "sandbox_id": sandbox["sandbox_id"], "retired": True, "physical_execution": "none"}:
        return False
    records, responses, results = [], [], {}
    for item in native:
        if set(item) != {"dispatch_id", "request_ref", "response_ref"}:
            raise ValueError("invalid native evidence fields")
        dispatch = next((d for d in model_dispatches if d["dispatch_id"] == item["dispatch_id"]), None)
        record = parse_json(_read_ref(artifacts, TENANT, task_id, item["request_ref"]))
        raw = decode_provider_payload(_read_ref(artifacts, TENANT, task_id, item["response_ref"]), approval.as_dict()["max_response_bytes"])
        usage = parse_nebius_usage(raw)
        if (dispatch is None or dispatch["input_digest"] != digest_json(record) or dispatch["result_ref"] != item["response_ref"]
                or dispatch["actual_units"] != envelope.charge(usage) or not envelope.within_token_bounds(usage)
                or set(record) != {"provider", "protocol", "endpoint", "payload"}
                or record["provider"] != "nebius" or record["protocol"] != "chat_completions"
                or record["endpoint"] != approval.as_dict()["endpoint"] or record["payload"]["model"] != approval.model):
            return False
        records.append(record)
        responses.append(parse_nebius_response(raw, approval.model))
    for dispatch in tools:
        result = parse_json(_read_ref(artifacts, TENANT, task_id, dispatch["result_ref"]))
        if not result.get("ok") or result.get("tool") != dispatch["kind"]:
            return False
        results[dispatch["kind"]] = result
    first, second = responses
    if (len(first.calls) != 1 or first.calls[0].name != "read_file" or first.calls[0].arguments != {"path": FIXTURE["path"]}
            or len(second.calls) != 1 or second.calls[0].name != "finish"
            or results["read_file"]["call_id"] != first.calls[0].call_id
            or results["finish"]["call_id"] != second.calls[0].call_id
            or results["read_file"]["value"] != {"path": FIXTURE["path"], "text": FIXTURE["text"],
                "digest": digest_bytes(FIXTURE["text"].encode()), "bytes": len(FIXTURE["text"].encode())}
            or results["finish"]["value"] != {"completion_proposal": second.calls[0].arguments["summary"], "verified": False}):
        return False
    original = records[0]["payload"]["messages"]
    continuation = records[1]["payload"]["messages"]
    assistant = first.raw["choices"][0]["message"]
    tool = {"role": "tool", "tool_call_id": first.calls[0].call_id,
            "content": canonical_bytes(results["read_file"]).decode()}
    if continuation != original + [assistant, tool]:
        return False
    checkpoints = snapshot["checkpoints"]
    if len(checkpoints) != 2:
        return False
    history = [{"role": "user", "content": "\n".join(expected_contract["requirements"])}]
    for turn, response in enumerate(responses):
        if records[turn] != _expected_native_request(approval, expected_contract, history):
            return False
        call = response.calls[0]
        history += [response.raw["choices"][0]["message"], {"role": "tool", "tool_call_id": call.call_id,
                    "content": canonical_bytes(results[call.name]).decode()}]
        checkpoint = next((c for c in checkpoints if c["manifest"]["next_turn"] == turn + 1), None)
        if checkpoint is None:
            return False
        saved = checkpoint["manifest"]
        payload = parse_json(_read_ref(artifacts, TENANT, task_id, saved["artifact_ref"]))
        workspace = parse_json(_read_ref(artifacts, TENANT, task_id, saved["workspace_ref"]))
        _linked_refs(artifacts, TENANT, task_id, payload)
        evidence = [{"request_ref": n["request_ref"], "response_ref": n["response_ref"]} for n in native[:turn + 1]]
        if (saved["completion_proposed"] is not (turn == 1) or saved["provider_artifacts"] != evidence
                or payload["messages"] != history or payload["evidence"] != evidence
                or payload["workspace_ref"] != saved["workspace_ref"]
                or workspace != {FIXTURE["path"]: FIXTURE["text"]}
                or payload["status"] != ("completion_proposed" if turn == 1 else "checkpointed")):
            return False
    return snapshot["budget"]["spent"] == sum(d["actual_units"] for d in snapshot["dispatches"]) and snapshot["budget"]["reserved"] == 0


def run_qualification(output):
    root = _existing_root(output)
    manifest = _manifest(root)
    _check_sources(manifest)
    if (root / "report.json").exists():
        return read_qualification_report(root)
    if (root / "started.json").exists():
        raise ValueError("qualification interrupted or already running; no retry")
    data = manifest.as_dict()
    if data["execution_deadline"] <= time.time() or not _fixture_valid(root):
        raise ValueError("qualification deadline or owned fixture invalid")
    _publish(root / "started.json", {"schema": 1, "manifest_digest": manifest.digest})
    artifacts = LocalArtifacts(root / "artifacts")
    store = RuntimeStore("sqlite:///" + str(root / "authority.sqlite"), artifacts)
    task_id = None
    try:
        approval = ProviderApproval.from_dict(data["provider_approval"])
        contract = _probe_contract(manifest)
        task = store.submit(TENANT, "offline-probe", contract)
        task_id = task["task_id"]
        store.set_graph(TENANT, task_id, 1, [{"node_id": "probe", "dependencies": [], "role": "patch", "allowed_paths": []}])
        grant = store.claim(TENANT, task_id, "probe", "probe-once", data["budget_units"], 300)
        error = None
        client = httpx.Client(transport=httpx.MockTransport(_mock_transport(approval)), trust_env=False, follow_redirects=False)
        try:
            if not _mock_client(client):
                raise PermissionError("offline transport isolation failed")
            adapter = approval.build_adapter("qualification-synthetic-key", enable_network=True, client=client)
            Harness(store, artifacts, max_turns=2, context_bytes=data["context_bytes"],
                    provider_envelopes={approval.model: approval.rate_snapshot}).run(
                        grant["owner"], store.get_task(TENANT, task_id)["contract"], Workspace(root / "fixture", []), adapter)
        except Exception as exc:
            error = ("transport_unknown" if isinstance(exc, httpx.TransportError) else
                     "protocol_or_usage_invalid" if isinstance(exc, (ValueError, RuntimeError)) else "probe_failed")
        finally:
            client.close()
            retired = artifacts.put_json(TENANT, task_id, {"schema": 1, "kind": "synchronous-offline-probe-retirement",
                    "sandbox_id": grant["sandbox_id"], "retired": True, "physical_execution": "none"})
            store.retire_sandbox(TENANT, grant["sandbox_id"], retired)
        snapshot = store.snapshot(TENANT, task_id)
        native = [{"dispatch_id": d["dispatch_id"], "request_ref": _ref(artifacts, task_id, d["input_digest"]),
                   "response_ref": d["result_ref"]} for d in sorted(snapshot["dispatches"], key=lambda d: d["dispatch_id"]) if d["kind"] == "model.nebius"]
        bundle = {"schema": 1, "manifest_digest": manifest.digest, "source_hashes": data["source_hashes"],
                  "snapshot": snapshot, "events": committed_repair_events(store, TENANT, task_id, snapshot),
                  "native": native, "error_category": error}
        # Unknown transport has no bytes: preserve it in the failed bundle, without inventing a receipt.
        _linked_refs(artifacts, TENANT, task_id, bundle)
        passed = _derive_pass(manifest, bundle, artifacts, root)
        report_ref = artifacts.put_json(TENANT, task_id, bundle)
        _publish(root / "report.json", {"schema": 1, "manifest_digest": manifest.digest, "report_ref": report_ref,
                                        "passed": passed, **FLAGS})
    finally:
        store.close()
    return read_qualification_report(root)


def read_qualification_report(output):
    root = _existing_root(output)
    manifest = _manifest(root)
    _check_sources(manifest)
    index = _read_json(root / "report.json", canonical=True)
    if (not isinstance(index, dict) or set(index) != {"schema", "manifest_digest", "report_ref", "passed", *FLAGS}
            or type(index["schema"]) is not int or index["schema"] != 1 or type(index["passed"]) is not bool
            or any(index[k] != v or type(index[k]) is not type(v) for k, v in FLAGS.items())
            or index["manifest_digest"] != manifest.digest):
        raise ValueError("invalid qualification report index")
    marker = _read_json(root / "started.json", canonical=True)
    if marker != {"schema": 1, "manifest_digest": manifest.digest} or type(marker["schema"]) is not int:
        raise ValueError("qualification start marker mismatch")
    artifacts = _artifacts(root)
    task_id = index["report_ref"]["task_id"]
    bundle = parse_json(_read_ref(artifacts, TENANT, task_id, index["report_ref"]))
    if (not isinstance(bundle, dict) or set(bundle) != {"schema", "manifest_digest", "source_hashes", "snapshot", "events", "native", "error_category"}
            or type(bundle["schema"]) is not int or bundle["schema"] != 1 or bundle["manifest_digest"] != manifest.digest
            or bundle["source_hashes"] != manifest.as_dict()["source_hashes"]
            or bundle["error_category"] not in {None, "transport_unknown", "protocol_or_usage_invalid", "probe_failed"}):
        raise ValueError("invalid qualification report bundle")
    with _snapshot_store(root, artifacts) as store:
        snapshot = store.snapshot(TENANT, task_id)
        if snapshot != bundle["snapshot"] or committed_repair_events(store, TENANT, task_id, snapshot) != bundle["events"]:
            raise ValueError("qualification runtime evidence differs from immutable report")
    passed = _derive_pass(manifest, bundle, artifacts, root)
    if index["passed"] is not passed:
        raise ValueError("qualification summary differs from independently derived evidence")
    return {**FLAGS, "passed": passed, "manifest_digest": manifest.digest, "report_digest": index["report_ref"]["digest"],
            "task_id": task_id, "native_requests": len(bundle["native"]), "error_category": bundle["error_category"],
            "synthetic_budget": snapshot["budget"], "supplied_evidence": manifest.as_dict()["provider_approval"]["evidence"],
            "live_gates": "pending account/catalog/current prices, authorization, spend bound and useful live repair"}


def create_qualification_handoff(output, repair_output):
    root = _existing_root(output)
    manifest = _manifest(root)
    _check_sources(manifest)
    report = read_qualification_report(root)
    if not report["passed"]:
        raise ValueError("successful offline qualification required")
    binding, approval = _repair_binding(repair_output)
    if binding != manifest.as_dict()["repair_binding"] or approval.as_dict() != manifest.as_dict()["provider_approval"]:
        raise ValueError("prepared repair binding drift")
    handoff = {"schema": 1, "advisory": True, "point_in_time_only": True, **FLAGS,
               "manifest_digest": manifest.digest, "report_digest": report["report_digest"],
               "source_hashes": manifest.as_dict()["source_hashes"], "repair_binding": binding,
               "provider_approval": approval.as_dict()}
    _publish(root / "handoff.json", handoff, converge=True)
    return handoff
