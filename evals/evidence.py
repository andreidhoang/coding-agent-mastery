"""Bounded local failure observations; digests bind bytes, never authority."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import math

from service.artifacts import canonical_bytes, digest_bytes, digest_json
from service.contracts import (
    digest,
    identity,
    strict_int,
    freeze,
    parse_json,
    validate_owner,
    Fenced,
    Unsupported,
    validate_contract,
)
from service.execution import tree_digest, safe_relative
from .manifest import FrozenManifest

SOURCE_MAX_BYTES = 16_777_216
ARTIFACT_MAX_BYTES = 8 * 1024 * 1024
ARTIFACT_TOTAL_BYTES = 32 * 1024 * 1024
TABLE_IDENTITIES = {
    "nodes": "node_id",
    "attempts": "attempt_id",
    "dispatches": "dispatch_id",
    "sandboxes": "sandbox_id",
    "candidates": "candidate_id",
    "checkpoints": "checkpoint_id",
    "verifications": "verification_id",
    "reviews": "review_id",
    "receipts": "receipt_id",
    "submissions": "key",
}
SNAPSHOT_FIELDS = {"task", "budget", "frontier", "recovery_frontier", "quarantined"} | (
    set(TABLE_IDENTITIES) - {"receipts", "submissions"}
)
OBSERVATION_FIELDS = set(
    "schema evidence_kind kind status reasons source_digest snapshot_digest events_digest source_provenance trust scope window subject identities artifacts accounting lineage assignment unavailable regression_eligible".split()
)
SUBJECT_FIELDS = set(
    "id event_id sequence generation attempt_id node_id dispatch_id verification_id effect_state billing_state outcome".split()
)
IDENTITY_FIELDS = set(
    "contract_digest base_revision candidate_id tree_digest grader_digest environment_digest input_digest".split()
)
ACCOUNT_FIELDS = set(
    "scope unit rate_snapshot rate_snapshot_digest spent_units reserved_units attempt_allowance_units unsettled_bound_units unknown_effect_count dispatches attempts input_tokens output_tokens infrastructure_cost".split()
)
TRUST = "local_caller_asserted_not_authenticated"


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("invalid closed schema")
    return value


def _label(value, maximum=128):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError("invalid bounded label")
    return value


def load_json_bytes(data):
    if not isinstance(data, bytes):
        raise ValueError("JSON bytes required")
    try:
        return freeze(parse_json(data))
    except (TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid JSON") from exc


def validate_source_hashes(value):
    if not isinstance(value, dict) or not 1 <= len(value) <= 64:
        raise ValueError("invalid source hashes")
    for name, sha in value.items():
        _label(name, 256)
        path = PurePosixPath(name)
        if path.is_absolute() or "\\" in name or any(p in ("", ".", "..") for p in name.split("/")):
            raise ValueError("invalid source hash label")
        digest(sha)
    return freeze(value)


def validate_lineage(value):
    _exact(value, {"family_id", "source_case_id", "parent_evidence_digests", "split", "held_out_eligible"})
    identity(value["family_id"])
    identity(value["source_case_id"])
    parents = value["parent_evidence_digests"]
    if not isinstance(parents, list) or len(parents) > 32:
        raise ValueError("invalid parent evidence")
    for parent in parents:
        digest(parent)
    if (
        len(set(parents)) != len(parents)
        or value["split"] != "development"
        or value["held_out_eligible"] is not False
    ):
        raise ValueError("invalid development lineage")
    return freeze(value)


def validate_artifact_ref(value, tenant_id, task_id, *, max_bytes=ARTIFACT_MAX_BYTES):
    _exact(value, {"tenant_id", "task_id", "digest", "size", "content_type"})
    identity(value["tenant_id"])
    identity(value["task_id"])
    if value["tenant_id"] != tenant_id or value["task_id"] != task_id:
        raise ValueError("invalid artifact scope")
    digest(value["digest"])
    strict_int(value["size"], "size", 0, max_bytes)
    _label(value["content_type"], 256)
    return freeze(value)


def validate_canonical_record(payload, record_digest, validator):
    if not isinstance(payload, bytes):
        raise ValueError("record payload must be bytes")
    digest(record_digest)
    data = load_json_bytes(payload)
    if canonical_bytes(data) != payload or digest_bytes(payload) != record_digest:
        raise ValueError("record identity mismatch")
    validator(data)
    return data


def _provenance(value):
    _exact(value, {"source_id", "origin", "source_hashes", "transformations", "redactions"})
    identity(value["source_id"])
    validate_source_hashes(value["source_hashes"])
    if (
        value["origin"] != "trusted_local_runtime_store"
        or value["transformations"] != []
        or value["redactions"] != []
    ):
        raise ValueError("unsupported source provenance")
    return freeze(value)


def _aggregate_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError("invalid nonnegative aggregate " + name)
    return value


def _finite(value):
    if type(value) not in (int, float) or value < 0:
        raise ValueError("invalid time")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError("invalid time") from exc
    if not finite:
        raise ValueError("invalid time")


def _validate_observation(data):
    _exact(data, OBSERVATION_FIELDS)
    if (
        type(data["schema"]) is not int
        or data["schema"] != 1
        or data["evidence_kind"] != "runtime_failure_observation"
    ):
        raise ValueError("unsupported failure observation")
    if (
        data["kind"] not in ("failed_verification", "unknown_dispatch")
        or data["status"] not in ("complete", "incomplete", "invalid")
        or data["trust"] != TRUST
    ):
        raise ValueError("invalid observation state")
    reasons = data["reasons"]
    if (
        not isinstance(reasons, list)
        or any(not isinstance(r, str) or not r for r in reasons)
        or reasons != sorted(set(reasons))
    ):
        raise ValueError("invalid reasons")
    if (
        type(data["regression_eligible"]) is not bool
        or data["regression_eligible"] != (data["status"] == "complete")
        or (data["status"] == "complete") != (not reasons)
    ):
        raise ValueError("inconsistent observation eligibility")
    for field in ("source_digest", "snapshot_digest", "events_digest"):
        digest(data[field])
    _provenance(data["source_provenance"])
    validate_lineage(data["lineage"])
    scope = _exact(
        data["scope"],
        {"service_incarnation", "tenant_id", "task_id", "current_generation", "frontier", "retained_from"},
    )
    for field in ("service_incarnation", "tenant_id", "task_id"):
        identity(scope[field])
    for field in ("current_generation", "frontier", "retained_from"):
        strict_int(scope[field], field, 1)
    window = _exact(data["window"], {"start_sequence", "end_sequence"})
    strict_int(window["start_sequence"], "start", 1, scope["frontier"])
    strict_int(window["end_sequence"], "end", window["start_sequence"], scope["frontier"])
    subject = _exact(data["subject"], SUBJECT_FIELDS)
    identity(subject["id"])
    for field in ("sequence", "generation"):
        if subject[field] is not None:
            strict_int(subject[field], field, 1)
    for field in SUBJECT_FIELDS - {
        "id",
        "sequence",
        "generation",
        "effect_state",
        "billing_state",
        "outcome",
    }:
        if subject[field] is not None:
            identity(subject[field])
    if (
        subject["effect_state"]
        not in (None, "in_flight", "unknown", "succeeded", "failed_known", "not_dispatched")
        or subject["billing_state"] not in (None, "reserved", "liability_unknown", "settled")
        or subject["outcome"] not in (None, "pass", "fail", "error")
    ):
        raise ValueError("invalid selected state")
    identities = _exact(data["identities"], IDENTITY_FIELDS)
    for field, value in identities.items():
        if value is not None:
            if field == "base_revision":
                _label(value, 512)
            elif field == "candidate_id":
                identity(value)
            else:
                digest(value)
    accounting = _exact(data["accounting"], ACCOUNT_FIELDS)
    if accounting["scope"] != "whole_task_at_frontier" or accounting["unit"] != "runtime_budget_units":
        raise ValueError("invalid accounting scope")
    if accounting["rate_snapshot"] is not None and not isinstance(accounting["rate_snapshot"], dict):
        raise ValueError("invalid rate snapshot")
    if accounting["rate_snapshot_digest"] != (
        None if accounting["rate_snapshot"] is None else digest_json(accounting["rate_snapshot"])
    ):
        raise ValueError("rate identity mismatch")
    total_fields = (
        "spent_units",
        "reserved_units",
        "attempt_allowance_units",
        "unsettled_bound_units",
        "unknown_effect_count",
    )
    accounting_unavailable = all(accounting[field] is None for field in total_fields)
    if any(accounting[field] is None for field in total_fields) and not accounting_unavailable:
        raise ValueError("partially unavailable accounting")
    if accounting_unavailable:
        if (
            data["status"] == "complete"
            or data["regression_eligible"]
            or "accounting_unavailable" not in reasons
        ):
            raise ValueError("inconsistent unavailable accounting")
        if not isinstance(data["unavailable"], dict) or any(
            data["unavailable"].get("accounting." + field) != "missing_source" for field in total_fields
        ):
            raise ValueError("unexplained unavailable accounting")
    else:
        for field in total_fields:
            if field == "unknown_effect_count":
                strict_int(accounting[field], field)
            else:
                _aggregate_int(accounting[field], field)
    for field in ("input_tokens", "output_tokens", "infrastructure_cost"):
        if accounting[field] is not None:
            raise ValueError("unsupported accounting units")
    aids, dids, attempt_index = set(), set(), {}
    if not isinstance(accounting["attempts"], list) or not isinstance(accounting["dispatches"], list):
        raise ValueError("invalid accounting arrays")
    for a in accounting["attempts"]:
        _exact(a, {"attempt_id", "node_id", "generation", "allowance_remaining"})
        identity(a["attempt_id"])
        identity(a["node_id"])
        strict_int(a["generation"], "generation", 1)
        if a["generation"] > scope["current_generation"]:
            raise ValueError("accounting generation outside task history")
        strict_int(a["allowance_remaining"], "allowance")
        if a["attempt_id"] in aids:
            raise ValueError("duplicate accounting attempt")
        aids.add(a["attempt_id"])
        attempt_index[a["attempt_id"]] = a
    for d in accounting["dispatches"]:
        _exact(
            d,
            {
                "dispatch_id",
                "attempt_id",
                "node_id",
                "generation",
                "kind",
                "effect_state",
                "billing_state",
                "bound_units",
                "actual_units",
                "receipt_id",
            },
        )
        for field in ("dispatch_id", "attempt_id", "node_id", "kind"):
            identity(d[field])
        strict_int(d["generation"], "generation", 1)
        strict_int(d["bound_units"], "bound")
        if d["actual_units"] is not None:
            strict_int(d["actual_units"], "actual")
        if d["receipt_id"] is not None:
            identity(d["receipt_id"])
        if d["dispatch_id"] in dids or (not accounting_unavailable and d["attempt_id"] not in aids):
            raise ValueError("invalid accounting dispatch")
        owner = attempt_index.get(d["attempt_id"])
        if owner is not None and (d["node_id"] != owner["node_id"] or d["generation"] != owner["generation"]):
            raise ValueError("accounting owner disagreement")
        dids.add(d["dispatch_id"])
        _dispatch_states(d)
    if not accounting_unavailable:
        calculated = _totals(accounting["attempts"], accounting["dispatches"])
        if any(accounting[k] != v for k, v in calculated.items()):
            raise ValueError("accounting record mismatch")
    inventory = data["artifacts"]
    if not isinstance(inventory, list) or len(inventory) > 256:
        raise ValueError("invalid artifact inventory")
    seen = set()
    for ref in inventory:
        _exact(ref, {"tenant_id", "task_id", "digest", "size", "status"})
        if (
            ref["tenant_id"] != scope["tenant_id"]
            or ref["task_id"] != scope["task_id"]
            or ref["status"] not in ("verified", "missing", "invalid")
        ):
            raise ValueError("invalid artifact inventory scope")
        digest(ref["digest"])
        strict_int(ref["size"], "size")
        if ref["status"] == "verified" and ref["size"] > ARTIFACT_MAX_BYTES:
            raise ValueError("verified artifact exceeds bound")
        if ref["digest"] in seen:
            raise ValueError("duplicate artifact")
        seen.add(ref["digest"])
    if sum(ref["size"] for ref in inventory if ref["status"] == "verified") > ARTIFACT_TOTAL_BYTES:
        raise ValueError("verified artifact aggregate exceeds bound")
    if inventory != sorted(inventory, key=lambda x: x["digest"]):
        raise ValueError("unsorted artifact inventory")
    unavailable = data["unavailable"]
    if not isinstance(unavailable, dict) or any(
        not isinstance(k, str)
        or v not in ("not_applicable", "not_recorded_by_runtime", "unassigned_local_run", "missing_source")
        for k, v in unavailable.items()
    ):
        raise ValueError("invalid unavailable metadata")
    for group in ("subject", "identities", "accounting"):
        for field, value in data[group].items():
            if value is None and group + "." + field not in unavailable:
                raise ValueError("unexplained null")
    if data["assignment"] is None:
        if unavailable.get("assignment") != "unassigned_local_run":
            raise ValueError("unexplained assignment")
    else:
        assignment = _exact(
            data["assignment"], {"manifest_digest", "planned_row", "runtime_submission_id", "binding_kind"}
        )
        digest(assignment["manifest_digest"])
        digest(assignment["runtime_submission_id"])
        if (
            not isinstance(assignment["planned_row"], dict)
            or assignment["binding_kind"] != "caller_declared_runtime_mapping"
        ):
            raise ValueError("invalid assignment")
        row = _exact(
            assignment["planned_row"],
            {
                "row_id",
                "task_id",
                "trial_id",
                "arm",
                "schedule_index",
                "base_commit",
                "grader_digest",
                "version_block",
                "submission_id",
            },
        )
        for field in ("row_id", "task_id", "submission_id", "version_block"):
            _label(row[field], 512)
        strict_int(row["trial_id"], "trial_id")
        strict_int(row["schedule_index"], "schedule_index")
        if row["arm"] not in ("bare", "coordinated_n1", "coordinated_n2", "coordinated_n4"):
            raise ValueError("invalid assignment arm")
        _label(row["base_commit"], 512)
        digest(row["grader_digest"])
        if (
            row["base_commit"] != identities["base_revision"]
            or row["grader_digest"] != identities["grader_digest"]
        ):
            raise ValueError("assignment identity mismatch")
    if data["status"] == "complete":
        if (
            type(subject["sequence"]) is not int
            or not window["start_sequence"] <= subject["sequence"] <= window["end_sequence"]
        ):
            raise ValueError("selected event outside window")
        if subject["generation"] is None or subject["generation"] > scope["current_generation"]:
            raise ValueError("selected generation outside task history")
        if scope["retained_from"] != 1:
            raise ValueError("incomplete retained history")
        if any(
            v is None
            for v in (
                identities["contract_digest"],
                identities["base_revision"],
                identities["grader_digest"],
                identities["environment_digest"],
                subject["event_id"],
                subject["generation"],
                subject["sequence"],
            )
        ) or any(ref["status"] != "verified" for ref in inventory):
            raise ValueError("incomplete eligible record")
        if data["kind"] == "failed_verification" and (
            subject["outcome"] != "fail"
            or any(identities[k] is None for k in ("candidate_id", "tree_digest"))
            or subject["verification_id"] != subject["id"]
        ):
            raise ValueError("invalid eligible verification")
        if data["kind"] == "unknown_dispatch" and (
            subject["effect_state"] != "unknown"
            or subject["dispatch_id"] != subject["id"]
            or identities["input_digest"] is None
        ):
            raise ValueError("invalid eligible Unknown")
        if data["kind"] == "unknown_dispatch":
            selected = [d for d in accounting["dispatches"] if d["dispatch_id"] == subject["dispatch_id"]]
            if len(selected) != 1 or any(
                selected[0][k] != subject[k]
                for k in ("generation", "attempt_id", "node_id", "effect_state", "billing_state")
            ):
                raise ValueError("selected dispatch projection disagreement")


@dataclass(frozen=True)
class FailureEvidence:
    payload: bytes
    digest: str

    def __post_init__(self):
        self.verify()

    @classmethod
    def freeze(cls, data):
        _validate_observation(data)
        payload = canonical_bytes(data)
        return cls(payload, digest_bytes(payload))

    def read(self):
        return load_json_bytes(self.payload)

    def verify(self):
        return validate_canonical_record(self.payload, self.digest, _validate_observation)


def _validate_owner(value):
    try:
        return validate_owner(value)
    except Fenced as exc:
        raise ValueError("invalid ownership tuple") from exc


def _dispatch_states(d):
    effect, billing, actual = d["effect_state"], d["billing_state"], d["actual_units"]
    if effect not in (
        "in_flight",
        "unknown",
        "succeeded",
        "failed_known",
        "not_dispatched",
    ) or billing not in ("reserved", "liability_unknown", "settled"):
        raise ValueError("invalid dispatch states")
    if (
        (billing == "settled") != (actual is not None)
        or (effect == "in_flight") != (billing == "reserved")
        or (effect == "not_dispatched" and actual not in (None, 0))
    ):
        raise ValueError("contradictory dispatch states")


def _totals(attempts, dispatches):
    allowances = sum(a["allowance_remaining"] for a in attempts)
    bound = sum(d["bound_units"] for d in dispatches if d["billing_state"] != "settled")
    return dict(
        spent_units=sum(d["actual_units"] for d in dispatches if d["billing_state"] == "settled"),
        reserved_units=allowances + bound,
        attempt_allowance_units=allowances,
        unsettled_bound_units=bound,
        unknown_effect_count=sum(d["effect_state"] == "unknown" for d in dispatches),
    )


def _assignment(value, source, contract, lineage):
    if value is None:
        return None
    _exact(value, {"manifest", "row_id", "runtime_submission_id"})
    manifest = value["manifest"]
    if not isinstance(manifest, FrozenManifest):
        raise ValueError("actual FrozenManifest required")
    manifest.verify()
    planned = manifest.read()
    if planned["split"] != "development":
        raise ValueError("development assignment required")
    _label(value["row_id"], 256)
    digest(value["runtime_submission_id"])
    rows = [r for r in planned["planned_rows"] if r["row_id"] == value["row_id"]]
    if len(rows) != 1:
        raise ValueError("ambiguous assignment")
    row = rows[0]
    tasks = [t for t in planned["tasks"] if t["task_id"] == row["task_id"]]
    if len(tasks) != 1:
        raise ValueError("ambiguous task assignment")
    task = tasks[0]
    if (
        any(
            row[k] != contract[runtime] or task[k] != contract[runtime]
            for k, runtime in (("base_commit", "base_revision"), ("grader_digest", "grader_digest"))
        )
        or task["repository"] != contract["repo_id"]
    ):
        raise ValueError("assignment does not bind runtime contract")
    submissions = [
        s
        for s in source["submissions"]
        if digest_json([source["tenant_id"], s["key"]]) == value["runtime_submission_id"]
        and s["task_id"] == source["task_id"]
    ]
    if len(submissions) != 1:
        raise ValueError("runtime submission mapping missing")
    if (
        task["repository"] == "synthetic-issue-tracker-v1"
        and lineage["family_id"] != "synthetic-issue-tracker-v1"
    ):
        raise ValueError("synthetic family lineage must be retained")
    return dict(
        manifest_digest=manifest.digest,
        planned_row=freeze(row),
        runtime_submission_id=value["runtime_submission_id"],
        binding_kind="caller_declared_runtime_mapping",
    )


def extract_failure_evidence(
    source, *, kind, subject_id, window, source_provenance, lineage, artifact_reader, assignment=None
):
    """Validate the entire retained cut, then select one failure at its causal event."""
    if kind not in ("failed_verification", "unknown_dispatch"):
        raise ValueError("unsupported failure kind")
    identity(subject_id, "subject_id")
    provenance = _provenance(source_provenance)
    lineage = validate_lineage(lineage)
    if not callable(artifact_reader):
        raise ValueError("trusted artifact reader required")
    try:
        encoded = canonical_bytes(source)
        source = load_json_bytes(encoded)
    except (TypeError, RecursionError) as exc:
        raise ValueError("invalid JSON source") from exc
    if len(encoded) > SOURCE_MAX_BYTES:
        raise ValueError("source exceeds byte limit")
    _exact(window, {"start_sequence", "end_sequence"})
    # A cut must expose a usable frontier and scope before selection can be defined.
    if not isinstance(source, dict) or not isinstance(source.get("capture"), dict):
        raise ValueError("source frontier missing")
    capture = source["capture"]
    frontier = strict_int(capture.get("frontier"), "frontier", 1)
    strict_int(window["start_sequence"], "start_sequence", 1, frontier)
    strict_int(window["end_sequence"], "end_sequence", window["start_sequence"], frontier)
    window = freeze(window)
    tenant_id, task_id = identity(source.get("tenant_id")), identity(source.get("task_id"))
    incarnation = identity(capture.get("service_incarnation"))
    retained = strict_int(capture.get("retained_from"), "retained_from", 1)
    invalid, incomplete = set(), set()

    def check(action, reason):
        try:
            return action()
        except (ValueError, KeyError, TypeError):
            # Only validators and JSON access run here; reader/database errors do not.
            invalid.add(reason)
            return None

    check(
        lambda: _exact(
            source,
            {
                "schema",
                "evidence_kind",
                "tenant_id",
                "task_id",
                "snapshot",
                "receipts",
                "submissions",
                "events",
                "capture",
            },
        ),
        "source_disagreement",
    )
    if (
        type(source.get("schema")) is not int
        or source.get("schema") != 1
        or source.get("evidence_kind") != "runtime_failure_source"
    ):
        invalid.add("source_disagreement")
    snapshot = source.get("snapshot", {})
    if check(lambda: _exact(snapshot, SNAPSHOT_FIELDS), "source_disagreement") is None:
        snapshot = snapshot if isinstance(snapshot, dict) else {}
    task = snapshot.get("task", {})
    if not isinstance(task, dict):
        invalid.add("invalid_identity")
        task = {}
    contract = task.get("contract", {}) if isinstance(task, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    generation = check(lambda: strict_int(task["generation"], "generation", 1), "invalid_identity") or 1
    if task.get("tenant_id") != tenant_id or task.get("task_id") != task_id:
        invalid.add("invalid_scope")
    if (
        task.get("event_sequence") != frontier
        or task.get("retained_from") != retained
        or snapshot.get("frontier") != {"service_incarnation": incarnation, "sequence": frontier}
    ):
        invalid.add("source_disagreement")
    if retained != 1:
        incomplete.add("retention_gap")
    check(lambda: digest(task["contract_digest"]), "invalid_identity")
    if task.get("contract_digest") != digest_json(contract):
        invalid.add("invalid_identity")
    for field in ("grader_digest", "environment_digest"):
        check(lambda field=field: digest(contract[field]), "invalid_identity")
    check(lambda: _label(contract["base_revision"], 512), "invalid_identity")
    check(lambda: strict_int(contract["budget_units"], "budget_units"), "accounting_mismatch")

    def validate_frozen_contract():
        try:
            validated = validate_contract(contract, now=0)
        except Unsupported as exc:
            raise ValueError("unsupported frozen contract") from exc
        if validated != contract:
            raise ValueError("incomplete frozen contract")

    check(validate_frozen_contract, "invalid_identity")
    for key, value in task.items():
        if key.endswith("_at") and value is not None:
            check(lambda value=value: _finite(value), "invalid_identity")

    def scope_walk(value):
        if isinstance(value, dict):
            if (
                "tenant_id" in value
                and value["tenant_id"] != tenant_id
                or "task_id" in value
                and value["task_id"] != task_id
            ):
                invalid.add("invalid_scope")
            if "service_incarnation" in value and value["service_incarnation"] != incarnation:
                incomplete.add("mixed_incarnation")
            for key, child in value.items():
                if key in ("files", "base_files"):
                    continue
                if (
                    key.endswith("_at")
                    or key in ("time", "lease_until", "execution_deadline", "review_deadline")
                ) and child is not None:
                    check(lambda child=child: _finite(child), "invalid_identity")
                scope_walk(child)
        elif isinstance(value, list):
            for child in value:
                scope_walk(child)

    scope_walk(source)
    tables, maps = {}, {}
    for name, field in TABLE_IDENTITIES.items():
        rows = source.get(name) if name in ("receipts", "submissions") else snapshot.get(name)
        if not isinstance(rows, list):
            invalid.add("source_disagreement")
            rows = []
        tables[name], maps[name] = rows, {}
        for row in rows:
            if name not in ("nodes", "receipts", "submissions") and (
                not isinstance(row, dict)
                or row.get("tenant_id") != tenant_id
                or row.get("task_id") != task_id
            ):
                invalid.add("invalid_scope")
            if name == "submissions" and (not isinstance(row, dict) or row.get("task_id") != task_id):
                invalid.add("invalid_scope")
            if isinstance(row, dict) and "generation" in row:
                row_generation = check(
                    lambda: strict_int(row["generation"], "row generation", 1), "invalid_identity"
                )
                if row_generation is not None and row_generation > generation:
                    invalid.add("invalid_identity")
            key = check(lambda row=row: identity(row[field]), "invalid_identity")
            if key is None:
                continue
            if key in maps[name]:
                invalid.add("duplicate_identity")
            maps[name][key] = row
        if (
            rows
            and check(lambda: sorted(rows, key=lambda r: (r[field], canonical_bytes(r))), "invalid_identity")
            != rows
        ):
            invalid.add("source_disagreement")
    events = source.get("events", [])
    if not isinstance(events, list):
        invalid.add("invalid_event")
        events = []
    event_ids, sequences = set(), []
    sound_events = []
    for event in events:
        if (
            check(
                lambda event=event: _exact(
                    event,
                    {
                        "event_id",
                        "sequence",
                        "kind",
                        "service_incarnation",
                        "tenant_id",
                        "task_id",
                        "time",
                        "payload",
                    },
                ),
                "invalid_event",
            )
            is None
        ):
            continue
        eid = check(lambda: identity(event["event_id"]), "invalid_event")
        sequence = check(lambda: strict_int(event["sequence"], "sequence", 1, frontier), "invalid_event")
        check(lambda: identity(event["kind"]), "invalid_event")
        check(lambda: _finite(event["time"]), "invalid_event")
        if not isinstance(event["payload"], dict):
            invalid.add("invalid_event")
            continue
        if eid in event_ids or sequence in sequences:
            invalid.add("duplicate_identity")
        event_ids.add(eid)
        sequences.append(sequence)
        sound_events.append(event)
    if len(sequences) != frontier or any(sequence != i for i, sequence in enumerate(sequences, 1)):
        incomplete.add("event_sequence_gap")
    check(
        lambda: _exact(
            capture,
            {
                "method",
                "schema_version",
                "service_incarnation",
                "frontier",
                "retained_from",
                "history_start",
                "history_end",
                "status",
                "reasons",
                "limits",
                "table_counts",
                "event_count",
                "source_bytes",
            },
        ),
        "source_disagreement",
    )
    expected_counts = {"tasks": 1, **{name: len(rows) for name, rows in tables.items()}}
    if (
        capture.get("method") != "runtime_store_repeatable_read_v1"
        or type(capture.get("schema_version")) is not int
        or capture.get("schema_version") != 2
        or capture.get("history_start") != 1
        or capture.get("history_end") != frontier
        or capture.get("table_counts") != expected_counts
        or capture.get("event_count") != len(events)
    ):
        invalid.add("source_disagreement")
    for field in ("history_start", "history_end", "event_count", "source_bytes"):
        check(lambda field=field: strict_int(capture[field], field), "source_disagreement")
    counts = capture.get("table_counts")
    if check(lambda: _exact(counts, expected_counts), "source_disagreement") is not None:
        for name, count in counts.items():
            check(lambda count=count: strict_int(count, "table count"), "source_disagreement")
    check(lambda: strict_int(task["event_sequence"], "task event sequence", 1), "invalid_identity")
    check(lambda: strict_int(task["retained_from"], "task retained from", 1), "invalid_identity")
    check(lambda: strict_int(snapshot["frontier"]["sequence"], "snapshot frontier", 1), "invalid_identity")
    for field in ("spent", "reserved", "limit"):
        check(
            lambda field=field: (
                strict_int(snapshot["budget"][field], "budget amount")
                if field == "limit"
                else _aggregate_int(snapshot["budget"][field], "budget amount")
            ),
            "accounting_mismatch",
        )
    limits = capture.get("limits", {})
    if not isinstance(limits, dict):
        limits = {}
    check(
        lambda: _exact(limits, {"max_rows", "max_events", "max_source_bytes", "page_size"}),
        "source_disagreement",
    )
    for name, lower, upper in (
        ("max_rows", 1, 10_000),
        ("max_events", 1, 10_000),
        ("max_source_bytes", 1024, SOURCE_MAX_BYTES),
        ("page_size", 1, 1000),
    ):
        check(
            lambda name=name, lower=lower, upper=upper: strict_int(limits[name], name, lower, upper),
            "source_disagreement",
        )
    body = {name: source.get(name) for name in ("snapshot", "receipts", "submissions", "events")}
    if capture.get("source_bytes") != len(canonical_bytes(body)):
        invalid.add("source_disagreement")
    if (
        type(limits.get("max_source_bytes")) is int
        and len(encoded) > limits["max_source_bytes"]
        or type(limits.get("max_rows")) is int
        and sum(expected_counts.values()) > limits["max_rows"]
        or type(limits.get("max_events")) is int
        and len(events) > limits["max_events"]
    ):
        raise ValueError("source exceeds declared capture limits")
    capture_reasons = sorted(incomplete & {"retention_gap", "event_sequence_gap", "mixed_incarnation"})
    if (
        capture.get("status") != ("incomplete" if capture_reasons else "complete")
        or capture.get("reasons") != capture_reasons
    ):
        invalid.add("source_disagreement")

    ledger_sound = all(
        len(maps[name]) == len(tables[name]) for name in ("attempts", "dispatches", "receipts")
    )
    if (
        not isinstance(snapshot.get("attempts"), list)
        or not isinstance(snapshot.get("dispatches"), list)
        or not isinstance(source.get("receipts"), list)
    ):
        ledger_sound = False

    def ledger_mark(reason, *, contradictory=True):
        nonlocal ledger_sound
        ledger_sound = False
        (invalid if contradictory else incomplete).add(reason)

    def ledger_check(action, reason):
        nonlocal ledger_sound
        try:
            return action()
        except (ValueError, KeyError, TypeError):
            ledger_sound = False
            invalid.add(reason)
            return None

    # Validate history-wide immutable joins, including rows outside the selected failure.
    event_index = {}
    for event in sound_events:
        payload = event["payload"]
        for field in ("candidate_id", "verification_id", "dispatch_id", "receipt_id", "attempt_id"):
            key = payload.get(field)
            if isinstance(key, str):
                event_index.setdefault((event["kind"], field, key), []).append(event)

    def matching(kind_name, field, key):
        return event_index.get((kind_name, field, key), [])

    for candidate in tables["candidates"]:

        def validate_candidate():
            manifest = candidate["manifest"]
            strict_int(candidate["generation"], "candidate generation", 1)
            if candidate["contract_digest"] != task["contract_digest"]:
                invalid.add("invalid_identity")
            for field in ("files", "base_files"):
                files = manifest[field]
                if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
                    raise ValueError("invalid text tree")
                for path in files:
                    safe_relative(path)
            if (
                tree_digest(manifest["files"]) != candidate["tree_digest"]
                or manifest["tree_digest"] != candidate["tree_digest"]
                or tree_digest(manifest["base_files"]) != contract["base_revision"]
                or manifest["base_revision"] != contract["base_revision"]
            ):
                invalid.add("invalid_identity")
            changed = sorted(
                p
                for p in set(manifest["files"]) | set(manifest["base_files"])
                if manifest["files"].get(p) != manifest["base_files"].get(p)
            )
            if manifest.get("changed_paths") != changed:
                invalid.add("invalid_identity")
            if (
                "environment_digest" in manifest
                and manifest["environment_digest"] != contract["environment_digest"]
            ):
                invalid.add("invalid_identity")
            if "manifest_digest" in manifest and manifest["manifest_digest"] != digest_json(
                {
                    k: v
                    for k, v in manifest.items()
                    if k not in ("manifest_digest", "artifact_ref", "candidate_id")
                }
            ):
                invalid.add("invalid_identity")
            if candidate["kind"] == "worker":
                owner = _validate_owner(candidate["owner"])
                if (
                    owner["generation"] != candidate["generation"]
                    or maps["attempts"].get(owner["attempt_id"], {}).get("owner") != owner
                ):
                    invalid.add("invalid_identity")
                if "owner" in manifest and manifest["owner"] != owner:
                    invalid.add("invalid_identity")
                causal = matching("candidate.accepted", "candidate_id", candidate["candidate_id"])
            elif candidate["kind"] == "integration":
                causal = matching("head.integrated", "candidate_id", candidate["candidate_id"])
                for parent_id in candidate["parent_candidate_ids"]:
                    parent = maps["candidates"].get(parent_id)
                    if parent is None:
                        incomplete.add("missing_causal_record")
                    elif parent["generation"] != candidate["generation"] or parent["kind"] != "worker":
                        invalid.add("invalid_identity")
            else:
                raise ValueError("invalid candidate kind")
            if not causal:
                incomplete.add("missing_causal_record")
            elif len(causal) != 1:
                invalid.add("duplicate_identity")
            elif candidate["kind"] == "integration" and (
                causal[0]["payload"].get("revision") != candidate["revision"]
                or causal[0]["payload"].get("parents") != candidate["parent_candidate_ids"]
            ):
                invalid.add("source_disagreement")

        check(validate_candidate, "invalid_identity")

    for verification in tables["verifications"]:

        def validate_verification():
            unsigned = {k: v for k, v in verification.items() if k not in ("verification_id", "recorded_at")}
            if (
                digest_json(unsigned) != verification["verification_id"]
                or verification["contract_digest"] != task["contract_digest"]
                or any(verification[k] != contract[k] for k in ("grader_digest", "environment_digest"))
            ):
                invalid.add("invalid_identity")
            strict_int(verification["generation"], "verification generation", 1)
            if verification["outcome"] not in ("pass", "fail", "error"):
                raise ValueError("invalid verification outcome")
            candidate = maps["candidates"].get(verification["candidate_id"])
            if candidate is None:
                incomplete.add("missing_causal_record")
            elif any(
                candidate[k] != verification[k] for k in ("generation", "tree_digest", "contract_digest")
            ):
                invalid.add("invalid_identity")
            events_for_row = matching(
                "verification.recorded", "verification_id", verification["verification_id"]
            )
            if not events_for_row:
                incomplete.add("missing_causal_record")
            elif len(events_for_row) != 1:
                invalid.add("duplicate_identity")
            elif events_for_row[0]["payload"] != verification:
                invalid.add("source_disagreement")
            elif candidate is not None:
                causal_kind = "candidate.accepted" if candidate["kind"] == "worker" else "head.integrated"
                if not any(
                    e["sequence"] < events_for_row[0]["sequence"]
                    for e in matching(causal_kind, "candidate_id", candidate["candidate_id"])
                ):
                    incomplete.add("missing_causal_record")

        check(validate_verification, "invalid_identity")

    for dispatch in tables["dispatches"]:

        def validate_dispatch_history():
            parameters = {
                k: dispatch[k]
                for k in ("owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units")
            }
            digest(dispatch["input_digest"])
            identity(dispatch["action_id"])
            if parameters != dispatch["parameters"]:
                ledger_mark("invalid_identity")
            intents = matching("dispatch.intent", "dispatch_id", dispatch["dispatch_id"])
            if not intents:
                ledger_mark("missing_causal_record", contradictory=False)
            elif len(intents) != 1:
                ledger_mark("duplicate_identity")
            elif intents[0]["payload"] != parameters:
                ledger_mark("source_disagreement")
            knowledge = dict(
                effect_state="in_flight",
                billing_state="reserved",
                actual_units=None,
                result_ref=None,
                receipt_id=None,
            )
            terminal = sorted(
                matching("dispatch.receipt", "dispatch_id", dispatch["dispatch_id"])
                + matching("dispatch.bound_violation", "dispatch_id", dispatch["dispatch_id"]),
                key=lambda e: e["sequence"],
            )
            for event in terminal:
                receipt = _exact(
                    event["payload"],
                    {"dispatch_id", "receipt_id", "effect_state", "actual_units", "result_ref"},
                )
                if receipt["receipt_id"] not in maps["receipts"]:
                    ledger_mark("missing_causal_record", contradictory=False)
                elif maps["receipts"][receipt["receipt_id"]] != receipt:
                    ledger_mark("source_disagreement")
                if intents and event["sequence"] <= intents[0]["sequence"]:
                    ledger_mark("invalid_event")
                if (
                    knowledge["effect_state"] in ("succeeded", "failed_known", "not_dispatched")
                    and receipt["effect_state"] != knowledge["effect_state"]
                    or knowledge["actual_units"] is not None
                    and receipt["actual_units"] not in (None, knowledge["actual_units"])
                ):
                    ledger_mark("source_disagreement")
                if (
                    knowledge["result_ref"] is not None
                    and receipt["result_ref"] is not None
                    and knowledge["result_ref"] != receipt["result_ref"]
                ):
                    ledger_mark("invalid_identity")
                if receipt["actual_units"] is not None:
                    strict_int(receipt["actual_units"], "actual")
                    knowledge["actual_units"] = receipt["actual_units"]
                if receipt["result_ref"] is not None:
                    knowledge["result_ref"] = receipt["result_ref"]
                knowledge.update(
                    effect_state=receipt["effect_state"],
                    receipt_id=receipt["receipt_id"],
                    billing_state="settled" if knowledge["actual_units"] is not None else "liability_unknown",
                )
                _dispatch_states(knowledge)
            if not terminal and dispatch["effect_state"] != "in_flight":
                ledger_mark("missing_causal_record", contradictory=False)
            elif any(dispatch[k] != v for k, v in knowledge.items()):
                ledger_mark("source_disagreement")

        ledger_check(validate_dispatch_history, "invalid_identity")

    for receipt in tables["receipts"]:

        def validate_receipt_row():
            _exact(receipt, {"dispatch_id", "receipt_id", "effect_state", "actual_units", "result_ref"})
            if receipt["dispatch_id"] not in maps["dispatches"]:
                ledger_mark("missing_causal_record", contradictory=False)
            causal = matching("dispatch.receipt", "receipt_id", receipt["receipt_id"]) + matching(
                "dispatch.bound_violation", "receipt_id", receipt["receipt_id"]
            )
            if not causal:
                ledger_mark("missing_causal_record", contradictory=False)
            elif len(causal) != 1:
                ledger_mark("duplicate_identity")
            elif causal[0]["payload"] != receipt:
                ledger_mark("source_disagreement")

        ledger_check(validate_receipt_row, "invalid_identity")
    for submission in tables["submissions"]:
        check(lambda submission=submission: digest(submission["request_digest"]), "invalid_identity")

    attempts, dispatches = [], []
    for attempt in tables["attempts"]:

        def project_attempt():
            owner = _validate_owner(attempt["owner"])
            if owner["generation"] > generation:
                raise ValueError("attempt generation outside task history")
            if any(attempt[k] != owner[k] for k in owner):
                raise ValueError("attempt owner disagreement")
            strict_int(attempt["allowance_remaining"], "allowance")
            if owner["node_id"] not in maps["nodes"]:
                ledger_mark("missing_causal_record", contradictory=False)
            return {k: attempt[k] for k in ("attempt_id", "node_id", "generation", "allowance_remaining")}

        projected = ledger_check(project_attempt, "invalid_identity")
        if projected is not None and projected["attempt_id"] not in {a["attempt_id"] for a in attempts}:
            attempts.append(projected)
    for dispatch in tables["dispatches"]:

        def project_dispatch():
            owner = _validate_owner(dispatch["owner"])
            if owner["generation"] > generation:
                raise ValueError("dispatch generation outside task history")
            attempt = maps["attempts"].get(dispatch["attempt_id"])
            if attempt is None:
                ledger_mark("missing_causal_record", contradictory=False)
                return None
            if attempt["owner"] != owner or owner["attempt_id"] != dispatch["attempt_id"]:
                raise ValueError("dispatch owner mismatch")
            strict_int(dispatch["bound_units"], "bound")
            if dispatch["actual_units"] is not None:
                strict_int(dispatch["actual_units"], "actual")
            result = {
                k: dispatch[k]
                for k in (
                    "dispatch_id",
                    "attempt_id",
                    "kind",
                    "effect_state",
                    "billing_state",
                    "bound_units",
                    "actual_units",
                    "receipt_id",
                )
            }
            result.update(node_id=owner["node_id"], generation=owner["generation"])
            for field in ("dispatch_id", "attempt_id", "kind"):
                identity(result[field])
            if result["receipt_id"] is not None:
                identity(result["receipt_id"])
            _dispatch_states(result)
            return result

        projected = ledger_check(project_dispatch, "accounting_mismatch")
        if projected is not None and projected["dispatch_id"] not in {d["dispatch_id"] for d in dispatches}:
            dispatches.append(projected)
    attempts.sort(key=lambda a: a["attempt_id"])
    dispatches.sort(key=lambda d: d["dispatch_id"])
    totals = _totals(attempts, dispatches)
    if snapshot.get("budget") != {
        "spent": totals["spent_units"],
        "reserved": totals["reserved_units"],
        "limit": contract.get("budget_units"),
    }:
        invalid.add("accounting_mismatch")
    if not ledger_sound:
        totals = dict.fromkeys(totals)
        incomplete.add("accounting_unavailable")
    rate = contract.get("rate_snapshot")
    if rate is not None and not isinstance(rate, dict):
        invalid.add("accounting_mismatch")
        rate = None
    accounting = dict(
        scope="whole_task_at_frontier",
        unit="runtime_budget_units",
        rate_snapshot=rate,
        rate_snapshot_digest=None if rate is None else digest_json(rate),
        **totals,
        dispatches=dispatches,
        attempts=attempts,
        input_tokens=None,
        output_tokens=None,
        infrastructure_cost=None,
    )

    # Preflight the complete reference closure before invoking the trusted reader.
    refs, invalid_refs = {}, set()

    def ref_walk(value):
        if isinstance(value, dict):
            if {"digest", "size", "tenant_id", "task_id"} <= set(value):
                try:
                    ref = validate_artifact_ref(value, tenant_id, task_id)
                except ValueError:
                    invalid.add("artifact_integrity")
                    if type(value.get("size")) is int and value["size"] > ARTIFACT_MAX_BYTES:
                        invalid.add("artifact_limit_exceeded")
                    if value.get("tenant_id") != tenant_id or value.get("task_id") != task_id:
                        invalid.add("invalid_scope")
                    return
                old = refs.get(ref["digest"])
                if old is not None and old["size"] != ref["size"]:
                    invalid.add("artifact_integrity")
                    invalid_refs.add(ref["digest"])
                refs[ref["digest"]] = ref
            for key, child in value.items():
                if key not in ("files", "base_files"):
                    ref_walk(child)
        elif isinstance(value, list):
            for child in value:
                ref_walk(child)

    ref_walk(source)
    over_limit = len(refs) > 256 or sum(ref["size"] for ref in refs.values()) > ARTIFACT_TOTAL_BYTES
    if over_limit:
        invalid.add("artifact_limit_exceeded")
    inventory, artifact_data, returned_bytes = [], {}, 0
    # Over-limit sources retain bounded metadata only, never perform any reads.
    for sha, ref in sorted(refs.items())[:256]:
        status = "invalid"
        if (
            not over_limit
            and sha not in invalid_refs
            and returned_bytes < ARTIFACT_TOTAL_BYTES
            and returned_bytes + ref["size"] <= ARTIFACT_TOTAL_BYTES
        ):
            try:
                raw = artifact_reader(tenant_id, task_id, sha)
            except (FileNotFoundError, KeyError):
                incomplete.add("artifact_missing")
                status = "missing"
            else:
                if not isinstance(raw, bytes):
                    invalid.add("artifact_integrity")
                else:
                    returned_bytes += len(raw)
                    if len(raw) > ARTIFACT_MAX_BYTES or returned_bytes > ARTIFACT_TOTAL_BYTES:
                        invalid.add("artifact_limit_exceeded")
                    elif len(raw) != ref["size"] or digest_bytes(raw) != sha:
                        invalid.add("artifact_integrity")
                    else:
                        status = "verified"
                        artifact_data[sha] = raw
        if (
            not over_limit
            and (
                returned_bytes >= ARTIFACT_TOTAL_BYTES or returned_bytes + ref["size"] > ARTIFACT_TOTAL_BYTES
            )
            and status != "verified"
        ):
            invalid.add("artifact_limit_exceeded")
        inventory.append({k: ref[k] for k in ("tenant_id", "task_id", "digest", "size")} | {"status": status})

    subject = dict.fromkeys(SUBJECT_FIELDS)
    subject["id"] = subject_id
    identities = dict.fromkeys(IDENTITY_FIELDS)
    identities.update(
        {k: contract.get(k) for k in ("base_revision", "grader_digest", "environment_digest")},
        contract_digest=task.get("contract_digest"),
    )
    selected_event = None
    if kind == "failed_verification":
        verification = maps["verifications"].get(subject_id)
        if verification is None:
            incomplete.add("subject_missing")
        else:

            def select_verification():
                nonlocal selected_event
                for field in ("generation",):
                    strict_int(verification[field], field, 1)
                subject.update(
                    verification_id=subject_id,
                    generation=verification["generation"],
                    outcome=verification["outcome"],
                )
                identities.update(
                    {
                        k: verification[k]
                        for k in (
                            "candidate_id",
                            "tree_digest",
                            "grader_digest",
                            "environment_digest",
                            "contract_digest",
                        )
                    }
                )
                if verification["outcome"] not in ("pass", "fail", "error"):
                    raise ValueError("invalid verdict")
                if verification["outcome"] != "fail":
                    incomplete.add("subject_not_supported_failure")
                unsigned = {
                    k: v for k, v in verification.items() if k not in ("verification_id", "recorded_at")
                }
                if digest_json(unsigned) != subject_id:
                    invalid.add("invalid_identity")
                matched = [
                    e
                    for e in sound_events
                    if e["kind"] == "verification.recorded"
                    and e["payload"].get("verification_id") == subject_id
                ]
                if not matched:
                    incomplete.add("missing_causal_record")
                elif len(matched) != 1:
                    invalid.add("duplicate_identity")
                else:
                    selected_event = matched[0]
                    if selected_event["payload"] != verification:
                        invalid.add("source_disagreement")
                candidate = maps["candidates"].get(verification["candidate_id"])
                if candidate is None:
                    incomplete.add("missing_causal_record")
                else:
                    manifest = candidate["manifest"]
                    if candidate["kind"] not in ("worker", "integration"):
                        invalid.add("invalid_identity")
                    for field in ("generation", "tree_digest", "contract_digest"):
                        if candidate[field] != verification[field]:
                            invalid.add("invalid_identity")
                    for field in ("files", "base_files"):
                        files = manifest[field]
                        if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
                            raise ValueError("invalid text tree")
                        for path in files:
                            safe_relative(path)
                    if (
                        tree_digest(manifest["files"]) != verification["tree_digest"]
                        or tree_digest(manifest["base_files"]) != contract["base_revision"]
                        or manifest["tree_digest"] != candidate["tree_digest"]
                        or manifest["base_revision"] != contract["base_revision"]
                    ):
                        invalid.add("invalid_identity")
                    if "manifest_digest" in manifest and manifest["manifest_digest"] != digest_json(
                        {
                            k: v
                            for k, v in manifest.items()
                            if k not in ("manifest_digest", "artifact_ref", "candidate_id")
                        }
                    ):
                        invalid.add("invalid_identity")
                    causal_kind = "candidate.accepted" if candidate["kind"] == "worker" else "head.integrated"
                    causal = [
                        e
                        for e in sound_events
                        if e["kind"] == causal_kind
                        and e["payload"].get("candidate_id") == candidate["candidate_id"]
                    ]
                    if (
                        not causal
                        or selected_event is not None
                        and not any(e["sequence"] < selected_event["sequence"] for e in causal)
                    ):
                        incomplete.add("missing_causal_record")
                    owner = candidate.get("owner")
                    if owner is not None:
                        owner = _validate_owner(owner)
                        subject.update(attempt_id=owner["attempt_id"], node_id=owner["node_id"])
                        if (
                            owner["generation"] != candidate["generation"]
                            or owner["attempt_id"] not in maps["attempts"]
                            or maps["attempts"][owner["attempt_id"]]["owner"] != owner
                        ):
                            invalid.add("invalid_identity")
                if (
                    any(verification[k] != contract[k] for k in ("grader_digest", "environment_digest"))
                    or verification["contract_digest"] != task["contract_digest"]
                ):
                    invalid.add("invalid_identity")
                ref = validate_artifact_ref(verification["evidence_ref"], tenant_id, task_id)
                raw = artifact_data.get(ref["digest"])
                if raw is not None:
                    try:
                        observed = load_json_bytes(raw)
                    except ValueError:
                        invalid.add("artifact_integrity")
                    else:
                        if not isinstance(observed, dict):
                            invalid.add("artifact_integrity")
                        elif (
                            "evidence_kind" in observed
                            or "kind" in observed
                            or not {"passed", "tree_digest", "grader_digest", "environment_digest"}
                            <= set(observed)
                        ):
                            incomplete.add("unsupported_verification_artifact")
                        elif (
                            type(observed["passed"]) is not bool
                            or observed["passed"] is not False
                            or any(
                                observed[k] != verification[k]
                                for k in ("tree_digest", "grader_digest", "environment_digest")
                            )
                        ):
                            invalid.add("artifact_integrity")

            check(select_verification, "invalid_identity")
    else:
        dispatch = maps["dispatches"].get(subject_id)
        if dispatch is None:
            incomplete.add("subject_missing")
        else:

            def select_dispatch():
                nonlocal selected_event
                owner = _validate_owner(dispatch["owner"])
                subject.update(
                    dispatch_id=subject_id,
                    generation=owner["generation"],
                    attempt_id=owner["attempt_id"],
                    node_id=owner["node_id"],
                    effect_state=dispatch["effect_state"],
                    billing_state=dispatch["billing_state"],
                )
                identities["input_digest"] = digest(dispatch["input_digest"])
                if dispatch["effect_state"] != "unknown":
                    incomplete.add("subject_not_supported_failure")
                parameters = {
                    k: dispatch[k]
                    for k in ("owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units")
                }
                if dispatch["parameters"] != parameters:
                    invalid.add("invalid_identity")
                intents = [
                    e
                    for e in sound_events
                    if e["kind"] == "dispatch.intent" and e["payload"].get("dispatch_id") == subject_id
                ]
                if not intents:
                    incomplete.add("missing_causal_record")
                elif len(intents) != 1:
                    invalid.add("duplicate_identity")
                elif intents[0]["payload"] != parameters:
                    invalid.add("source_disagreement")
                receipt_events = sorted(
                    [
                        e
                        for e in sound_events
                        if e["kind"] in ("dispatch.receipt", "dispatch.bound_violation")
                        and e["payload"].get("dispatch_id") == subject_id
                    ],
                    key=lambda e: e["sequence"],
                )
                if not receipt_events:
                    incomplete.add("missing_causal_record")
                else:
                    knowledge = dict(
                        effect_state="in_flight",
                        billing_state="reserved",
                        actual_units=None,
                        result_ref=None,
                        receipt_id=None,
                    )
                    for event in receipt_events:
                        receipt = _exact(
                            event["payload"],
                            {"dispatch_id", "receipt_id", "effect_state", "actual_units", "result_ref"},
                        )
                        identity(receipt["receipt_id"])
                        if receipt["receipt_id"] not in maps["receipts"]:
                            incomplete.add("missing_causal_record")
                        elif maps["receipts"][receipt["receipt_id"]] != receipt:
                            invalid.add("source_disagreement")
                        if intents and event["sequence"] <= intents[0]["sequence"]:
                            invalid.add("invalid_event")
                        old_effect, old_actual = knowledge["effect_state"], knowledge["actual_units"]
                        if (
                            old_effect in ("succeeded", "failed_known", "not_dispatched")
                            and receipt["effect_state"] != old_effect
                            or old_actual is not None
                            and receipt["actual_units"] not in (None, old_actual)
                        ):
                            invalid.add("source_disagreement")
                        if (
                            knowledge["result_ref"] is not None
                            and receipt["result_ref"] is not None
                            and knowledge["result_ref"] != receipt["result_ref"]
                        ):
                            invalid.add("invalid_identity")
                        if receipt["actual_units"] is not None:
                            strict_int(receipt["actual_units"], "actual")
                            knowledge["actual_units"] = receipt["actual_units"]
                        if receipt["result_ref"] is not None:
                            knowledge["result_ref"] = receipt["result_ref"]
                        knowledge.update(
                            effect_state=receipt["effect_state"],
                            receipt_id=receipt["receipt_id"],
                            billing_state="settled"
                            if knowledge["actual_units"] is not None
                            else "liability_unknown",
                        )
                        _dispatch_states(knowledge)
                    selected_event = receipt_events[-1]
                    if any(dispatch[k] != v for k, v in knowledge.items()):
                        invalid.add("source_disagreement")

            check(select_dispatch, "invalid_identity")
    if selected_event is not None:
        subject.update(event_id=selected_event["event_id"], sequence=selected_event["sequence"])
        if not window["start_sequence"] <= selected_event["sequence"] <= window["end_sequence"]:
            incomplete.add("subject_outside_window")
    missing_projections = set()
    for group, values in (("subject", subject), ("identities", identities)):
        for field, value in list(values.items()):
            if value is None:
                continue
            try:
                if group == "identities":
                    if field == "base_revision":
                        _label(value, 512)
                    elif field == "candidate_id":
                        identity(value)
                    else:
                        digest(value)
                elif field in ("generation", "sequence"):
                    strict_int(value, field, 1, generation if field == "generation" else frontier)
                elif field == "effect_state":
                    if value not in ("in_flight", "unknown", "succeeded", "failed_known", "not_dispatched"):
                        raise ValueError("invalid effect state")
                elif field == "billing_state":
                    if value not in ("reserved", "liability_unknown", "settled"):
                        raise ValueError("invalid billing state")
                elif field == "outcome":
                    if value not in ("pass", "fail", "error"):
                        raise ValueError("invalid verification outcome")
                else:
                    identity(value)
            except ValueError:
                invalid.add("invalid_identity")
                values[field] = None
                missing_projections.add(group + "." + field)
    if (
        contract.get("repo_id") == "synthetic-issue-tracker-v1"
        and lineage["family_id"] != "synthetic-issue-tracker-v1"
    ):
        raise ValueError("synthetic family lineage must be retained")
    assignment_data = _assignment(assignment, source, contract, lineage)
    unavailable = {}
    for group, values in (("subject", subject), ("identities", identities), ("accounting", accounting)):
        for field, value in values.items():
            if value is None:
                unavailable[group + "." + field] = (
                    "not_recorded_by_runtime" if group == "accounting" else "not_applicable"
                )
    if not ledger_sound:
        for field in totals:
            unavailable["accounting." + field] = "missing_source"
    for field in missing_projections:
        unavailable[field] = "missing_source"
    if assignment_data is None:
        unavailable["assignment"] = "unassigned_local_run"
    status = "invalid" if invalid else "incomplete" if incomplete else "complete"
    data = dict(
        schema=1,
        evidence_kind="runtime_failure_observation",
        kind=kind,
        status=status,
        reasons=sorted(invalid | incomplete),
        source_digest=digest_bytes(encoded),
        snapshot_digest=digest_json(source.get("snapshot")),
        events_digest=digest_json(source.get("events")),
        source_provenance=provenance,
        trust=TRUST,
        scope=dict(
            service_incarnation=incarnation,
            tenant_id=tenant_id,
            task_id=task_id,
            current_generation=generation,
            frontier=frontier,
            retained_from=retained,
        ),
        window=window,
        subject=subject,
        identities=identities,
        artifacts=inventory,
        accounting=accounting,
        lineage=lineage,
        assignment=assignment_data,
        unavailable=unavailable,
        regression_eligible=status == "complete",
    )
    return FailureEvidence.freeze(data)
