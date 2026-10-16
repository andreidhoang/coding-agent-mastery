"""Durable authority and liabilities using one deliberately coarse writer lock.

Every mutation locks the persisted service guard. SQLite uses BEGIN IMMEDIATE;
PostgreSQL uses SELECT FOR UPDATE. Provider/artifact operations run outside locks.
Schema 2 requires an explicit offline migration for schema-1 databases.
Writer protocol fences are a compatibility gate, not a security capability.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import Table, Column, String, Integer, JSON, MetaData
from .artifacts import canonical_bytes, digest_json
from .contracts import (
    Conflict,
    Fenced,
    BudgetExceeded,
    CapacityExceeded,
    NotFound,
    Unsupported,
    ResetRequired,
    freeze,
    strict_int,
    identity,
    digest,
    validate_contract,
    validate_owner,
)

from .migrations.v2_identity import (
    SCHEMA_VERSION,
    install_writer_fences,
    record_key,
    register_sqlite_protocol,
    set_writer_protocol,
)

metadata = MetaData()
schema_versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True))
authority = Table(
    "service_authority",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("data", JSON, nullable=False),
)
TABLES = {}
for name in (
    "tasks",
    "submissions",
    "nodes",
    "claims",
    "attempts",
    "sandboxes",
    "dispatches",
    "receipts",
    "candidates",
    "verifications",
    "reviews",
    "review_decisions",
    "checkpoints",
    "outbox",
):
    TABLES[name] = Table(
        name,
        metadata,
        Column("id", String(256), primary_key=True),
        Column("tenant_id", String(128), nullable=False, index=True),
        Column("task_id", String(128), nullable=False, index=True),
        Column("data", JSON, nullable=False),
    )
event_rows = Table(
    "task_events",
    metadata,
    Column("event_id", String(128), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("task_id", String(128), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("data", JSON, nullable=False),
    sa.UniqueConstraint("tenant_id", "task_id", "sequence"),
)


def _id() -> str:
    return uuid.uuid4().hex


class RuntimeStore:
    def __init__(
        self,
        url: str,
        artifact_store=None,
        *,
        service_slot_limit: int = 16,
        tenant_slot_limit: int = 8,
        service_budget_units: int = 10**9,
        tenant_budget_units: int = 10**8,
        admission_policy: dict | None = None,
    ):
        from .admission import validate_admission_policy
        requested_policy = validate_admission_policy(admission_policy) if admission_policy is not None else None
        for name, value in locals().copy().items():
            if name.endswith("_limit") or name.endswith("_units"):
                strict_int(value, name)
        self.artifact_store = artifact_store
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = sa.create_engine(url, **kwargs)
        if self.engine.dialect.name not in ("sqlite", "postgresql"):
            raise Unsupported("only SQLite and PostgreSQL authority stores are supported")
        if self.engine.dialect.name == "sqlite":

            @sa.event.listens_for(self.engine, "connect")
            def sqlite_setup(dbapi, _):
                register_sqlite_protocol(dbapi)
                dbapi.execute("PRAGMA foreign_keys=ON")
                dbapi.execute("PRAGMA busy_timeout=30000")

        # Inspect before any DDL/DML; an absent version never means old records
        # can safely be reinterpreted as a newly initialized schema.
        try:
            with self.engine.connect() as c:
                self._bootstrap_versions(c)
        except BaseException:
            self.engine.dispose()
            raise
        initial = {
            "service_incarnation": _id(),
            "accept_new_tasks": True,
            "execution_enabled": True,
            "quarantined": False,
            "service_slot_limit": service_slot_limit,
            "tenant_slot_limit": tenant_slot_limit,
            "service_budget_units": service_budget_units,
            "tenant_budget_units": tenant_budget_units,
            "cursor_secret": _id() + _id(),
            "recovery_frontier": None,
            "reconciliation_evidence": None,
        }
        if requested_policy is not None:
            initial.update(admission_policy=requested_policy, admission_policy_digest=digest_json(requested_policy))
        with self.engine.connect() as c:
            if c.dialect.name == "sqlite":
                c.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                c.begin()
            try:
                if c.dialect.name == "postgresql":
                    # Initial creation has no authority row yet. Serialize its
                    # insertion plus trigger DDL without concurrent lock upgrades.
                    c.exec_driver_sql(
                        "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || current_schema() || ':cam-bootstrap', 0))"
                    )
                # Recheck under bootstrap serialization before create_all or
                # inserting the authority/version rows, including preflight races.
                self._bootstrap_versions(c)
                metadata.create_all(c)
                set_writer_protocol(c)
                dialect = self.engine.dialect.name
                insert = __import__("sqlalchemy.dialects." + dialect, fromlist=["insert"]).insert
                c.execute(
                    insert(authority)
                    .values(id=1, data=initial)
                    .on_conflict_do_nothing(index_elements=[authority.c.id])
                )
                current_authority = c.execute(
                    sa.select(authority.c.data).where(authority.c.id == 1).with_for_update()
                ).scalar_one()
                from .admission import persisted_admission_policy
                persisted_policy = persisted_admission_policy(current_authority)
                if requested_policy is not None and persisted_policy != requested_policy:
                    raise Unsupported("requested admission policy differs from existing store")
                versions = c.execute(sa.select(schema_versions.c.version)).scalars().all()
                if versions and versions != [SCHEMA_VERSION]:
                    raise Unsupported("writer schema version changed during initialization")
                if not versions:
                    c.execute(schema_versions.insert().values(version=SCHEMA_VERSION))
                    install_writer_fences(c, [schema_versions, authority, event_rows, *TABLES.values()])
                self.execution_incarnation = current_authority["service_incarnation"]
                c.commit()
            except BaseException:
                c.rollback()
                self.engine.dispose()
                raise

    @staticmethod
    def _bootstrap_versions(c):
        inspector = sa.inspect(c)
        versions = (
            c.execute(sa.select(schema_versions.c.version)).scalars().all()
            if inspector.has_table(schema_versions.name)
            else []
        )
        if versions and versions != [SCHEMA_VERSION]:
            raise Unsupported("unsupported schema version; run explicit offline schema 1 to 2 migration")
        if not versions:
            for table in (authority, event_rows, *TABLES.values()):
                if (
                    inspector.has_table(table.name)
                    and c.execute(sa.select(sa.literal(1)).select_from(table).limit(1)).first() is not None
                ):
                    raise Unsupported(
                        "unversioned authority records require explicit operator recovery; refusing initialization"
                    )
        return versions

    def close(self):
        self.engine.dispose()

    @contextmanager
    def _tx(self):
        with self.engine.connect() as c:
            if c.dialect.name == "sqlite":
                c.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                c.begin()
            try:
                set_writer_protocol(c)
                if c.execute(sa.select(schema_versions.c.version)).scalars().all() != [SCHEMA_VERSION]:
                    raise Unsupported("writer schema version changed; controller restart required")
                guard = c.execute(
                    sa.select(authority.c.data).where(authority.c.id == 1).with_for_update()
                ).scalar_one()
                yield c, freeze(guard)
                c.commit()
            except BaseException:
                c.rollback()
                raise

    @contextmanager
    def _read(self):
        """One consistent snapshot for compound status/event reads."""
        with self.engine.connect() as c:
            if c.dialect.name == "sqlite":
                c.exec_driver_sql("BEGIN")
            else:
                c = c.execution_options(isolation_level="REPEATABLE READ")
                c.begin()
            try:
                yield c
            finally:
                c.rollback()

    def _now(self, c) -> float:
        if c.dialect.name == "postgresql":
            return float(c.execute(sa.text("SELECT EXTRACT(EPOCH FROM clock_timestamp())")).scalar_one())
        return float(c.execute(sa.text("SELECT (julianday('now') - 2440587.5) * 86400.0")).scalar_one())

    def _get(self, c, name, record_id, tenant_id=None, task_id=None):
        table = TABLES[name]
        if name in ("dispatches", "candidates") and tenant_id is not None:
            record_id = record_key(tenant_id, record_id)
        query = sa.select(table.c.data).where(table.c.id == record_id)
        if tenant_id is not None:
            query = query.where(table.c.tenant_id == tenant_id)
        if task_id is not None:
            query = query.where(table.c.task_id == task_id)
        value = c.execute(query).scalar_one_or_none()
        if value is None:
            raise NotFound(f"{name} record not found")
        return freeze(value)

    def _list(self, c, name, tenant_id=None, task_id=None):
        table = TABLES[name]
        query = sa.select(table.c.data).order_by(table.c.id)
        if tenant_id is not None:
            query = query.where(table.c.tenant_id == tenant_id)
        if task_id is not None:
            query = query.where(table.c.task_id == task_id)
        return [freeze(x) for x in c.execute(query).scalars()]

    def _save(self, c, name, record_id, tenant_id, task_id, data, *, new=False):
        table = TABLES[name]
        if name in ("dispatches", "candidates"):
            record_id = record_key(tenant_id, record_id)
        data = freeze(data)
        if new:
            c.execute(table.insert().values(id=record_id, tenant_id=tenant_id, task_id=task_id, data=data))
        else:
            result = c.execute(
                table.update()
                .where(table.c.id == record_id, table.c.tenant_id == tenant_id, table.c.task_id == task_id)
                .values(data=data)
            )
            if result.rowcount != 1:
                raise NotFound(f"{name} record not found")

    def _task(self, c, tenant_id, task_id):
        return self._get(c, "tasks", task_id, tenant_id, task_id)

    def _event(self, c, guard, tenant_id, task_id, kind, payload):
        task = self._task(c, tenant_id, task_id)
        task["event_sequence"] += 1
        self._save(c, "tasks", task_id, tenant_id, task_id, task)
        event = {
            "event_id": _id(),
            "sequence": task["event_sequence"],
            "kind": kind,
            "service_incarnation": guard["service_incarnation"],
            "tenant_id": tenant_id,
            "task_id": task_id,
            "time": self._now(c),
            "payload": freeze(payload),
        }
        c.execute(
            event_rows.insert().values(
                event_id=event["event_id"],
                tenant_id=tenant_id,
                task_id=task_id,
                sequence=event["sequence"],
                data=event,
            )
        )
        return event

    def _command(self, c, guard, task, kind, payload, command_id=None):
        command_id = command_id or _id()
        value = {
            "command_id": command_id,
            "tenant_id": task["tenant_id"],
            "task_id": task["task_id"],
            "generation": task["generation"],
            "service_incarnation": guard["service_incarnation"],
            "kind": kind,
            "payload": freeze(payload),
            "payload_digest": digest_json(payload),
            "acked": False,
            "created_at": self._now(c),
            "task_sequence": self._task(c, task["tenant_id"], task["task_id"])["event_sequence"],
        }
        self._save(c, "outbox", command_id, task["tenant_id"], task["task_id"], value, new=True)
        return command_id

    def _eligible(self, c, guard, task, generation, *, allow_expired=False):
        if self.execution_incarnation != guard["service_incarnation"]:
            raise Fenced("pre-restore control-plane authority revoked; construct a fresh controller")
        if not guard["execution_enabled"] or guard["quarantined"]:
            raise Fenced("service execution is quarantined")
        if task["generation"] != generation or task["execution_state"] not in ("queued", "running"):
            raise Fenced("task execution authority revoked")
        decision_time = self._now(c)
        if not allow_expired and decision_time > task["contract"]["execution_deadline"]:
            raise Fenced("database execution deadline elapsed")
        return decision_time

    def _owner(self, c, guard, owner):
        owner = validate_owner(owner)
        task = self._task(c, owner["tenant_id"], owner["task_id"])
        self._eligible(c, guard, task, owner["generation"])
        if owner["service_incarnation"] != guard["service_incarnation"]:
            raise Fenced("old service incarnation")
        attempt = self._get(c, "attempts", owner["attempt_id"], owner["tenant_id"], owner["task_id"])
        if (
            attempt["owner"] != owner
            or attempt["status"] != "running"
            or self._now(c) > attempt["lease_until"]
        ):
            raise Fenced("attempt ownership or lease revoked")
        node = self._get(
            c, "nodes", owner["task_id"] + ":" + owner["node_id"], owner["tenant_id"], owner["task_id"]
        )
        if node["node_epoch"] != owner["node_epoch"] or node.get("attempt_id") != owner["attempt_id"]:
            raise Fenced("node epoch revoked")
        self._dependencies(c, task, node)
        return owner, task, node, attempt

    def _dependencies(self, c, task, node):
        for dep in node["dependencies"]:
            parent = self._get(c, "nodes", task["task_id"] + ":" + dep, task["tenant_id"], task["task_id"])
            if parent["status"] != "completed" or parent["generation"] != task["generation"]:
                raise Fenced("dependency frontier is not accepted")

    def _budget(self, c, tenant_id=None, task_id=None):
        attempts = self._list(c, "attempts", tenant_id, task_id)
        dispatches = self._list(c, "dispatches", tenant_id, task_id)
        reserved = sum(a["allowance_remaining"] for a in attempts)
        reserved += sum(d["bound_units"] for d in dispatches if d["billing_state"] != "settled")
        spent = sum(d["actual_units"] for d in dispatches if d["billing_state"] == "settled")
        return {"spent": spent, "reserved": reserved}

    def _reserve(self, c, guard, task, units):
        for tenant, task_id, limit in (
            (None, None, guard["service_budget_units"]),
            (task["tenant_id"], None, guard["tenant_budget_units"]),
            (task["tenant_id"], task["task_id"], task["contract"]["budget_units"]),
        ):
            account = self._budget(c, tenant, task_id)
            if account["spent"] + account["reserved"] + units > limit:
                raise BudgetExceeded("hierarchical allowance exhausted")

    def _references(self, tenant_id, task_id, value):
        """Check immutable bytes before a transaction; no object-storage RPC under lock."""
        references = []

        def walk(x):
            if isinstance(x, dict):
                if {"digest", "size", "tenant_id", "task_id"} <= set(x):
                    if x["tenant_id"] != tenant_id or x["task_id"] != task_id:
                        raise NotFound("artifact reference not authorized for this task")
                    digest(x["digest"])
                    strict_int(x["size"], "artifact size")
                    if self.artifact_store is None:
                        raise Unsupported("artifact references require an artifact store")
                    data = self.artifact_store.get(tenant_id, task_id, x["digest"])
                    if len(data) != x["size"] or hashlib.sha256(data).hexdigest() != x["digest"]:
                        raise Conflict("artifact integrity mismatch")
                    references.append(freeze(x))
                for child in x.values():
                    walk(child)
            elif isinstance(x, list):
                for child in x:
                    walk(child)

        walk(value)
        return references

    def submit(self, tenant_id, key, contract):
        identity(tenant_id, "tenant_id")
        identity(key, "submission key")
        body = freeze(contract)
        request_digest = digest_json(body)
        submission_id = digest_json([tenant_id, key])
        with self._tx() as (c, guard):
            try:
                old = self._get(c, "submissions", submission_id, tenant_id)
            except NotFound:
                old = None
            if old:
                if old["request_digest"] != request_digest:
                    raise Conflict("submission key binds a different contract")
                return self._task(c, tenant_id, old["task_id"])
            if self.execution_incarnation != guard["service_incarnation"]:
                raise Fenced("pre-restore admission controller revoked")
            if not guard["accept_new_tasks"] or guard["quarantined"]:
                raise CapacityExceeded("service admission disabled")
            frozen = validate_contract(body, self._now(c))
            if self._now(c) > frozen["execution_deadline"]:
                raise Fenced("execution deadline already elapsed")
            from .admission import persisted_admission_policy
            policy = persisted_admission_policy(guard)
            if policy is not None:
                table = TABLES["tasks"]
                pending = table.c.data["execution_state"].as_string().in_(("queued", "running"))
                service_count = c.execute(sa.select(sa.func.count()).select_from(table).where(pending)).scalar_one()
                tenant_count = c.execute(sa.select(sa.func.count()).select_from(table).where(
                    pending, table.c.tenant_id == tenant_id)).scalar_one()
                if service_count >= policy["service_pending_limit"] or tenant_count >= policy["tenant_pending_limit"]:
                    raise CapacityExceeded("pending task capacity exhausted")
            task_id = _id()
            task = {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "generation": 1,
                "contract": frozen,
                "contract_digest": digest_json(frozen),
                "execution_state": "queued",
                "review_state": "none",
                "event_sequence": 0,
                "head_revision": 0,
                "head_candidate_id": None,
                "created_at": self._now(c),
                "cancel_requested_at": None,
                "authority_revoked_at": None,
                "quiescence_confirmed_at": None,
                "retained_from": 1,
            }
            self._save(c, "tasks", task_id, tenant_id, task_id, task, new=True)
            self._save(
                c,
                "submissions",
                submission_id,
                tenant_id,
                task_id,
                {"key": key, "request_digest": request_digest, "task_id": task_id},
                new=True,
            )
            self._event(
                c, guard, tenant_id, task_id, "task.submitted", {"contract_digest": task["contract_digest"]}
            )
            self._command(c, guard, task, "start", {"task_id": task_id})
            return self._task(c, tenant_id, task_id)

    def get_task(self, tenant_id, task_id):
        with self._read() as c:
            task = self._task(c, tenant_id, task_id)
            task["budget"] = {
                **self._budget(c, tenant_id, task_id),
                "limit": task["contract"]["budget_units"],
            }
            task["physical_slots"] = sum(
                s["status"] != "retired" for s in self._list(c, "sandboxes", tenant_id, task_id)
            )
            return task

    def set_graph(self, tenant_id, task_id, generation, nodes):
        strict_int(generation, "generation", 1)
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("graph must contain nodes")
        graph = []
        seen = set()
        for entry in nodes:
            entry = freeze(entry)
            node_id = identity(entry.pop("id", entry.get("node_id")), "node_id")
            entry["node_id"] = node_id
            dependencies = entry.pop("deps", entry.get("dependencies", []))
            if (
                not isinstance(dependencies, list)
                or any(not isinstance(x, str) for x in dependencies)
                or len(set(dependencies)) != len(dependencies)
            ):
                raise ValueError("invalid dependencies")
            entry["dependencies"] = dependencies
            if node_id in seen:
                raise Conflict("duplicate node identity")
            seen.add(node_id)
            graph.append(entry)
        frontier = set()
        while len(frontier) < len(graph):
            ready = {n["node_id"] for n in graph if set(n["dependencies"]) <= frontier} - frontier
            if not ready:
                raise Conflict("graph is cyclic or references missing dependencies")
            frontier |= ready
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            self._eligible(c, guard, task, generation)
            if len(graph) > task["contract"]["max_nodes"]:
                raise CapacityExceeded("graph exceeds frozen node limit")
            existing = self._list(c, "nodes", tenant_id, task_id)
            if existing:
                if task.get("graph_digest") != digest_json(graph):
                    raise Conflict("graph is already frozen")
                return {"task_id": task_id, "generation": generation, "nodes": existing}
            task["graph_digest"] = digest_json(graph)
            task["execution_state"] = "running"
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            for entry in graph:
                entry.update(
                    generation=generation, node_epoch=0, status="pending", attempt_id=None, candidate_id=None
                )
                self._save(c, "nodes", task_id + ":" + entry["node_id"], tenant_id, task_id, entry, new=True)
            self._event(c, guard, tenant_id, task_id, "graph.frozen", {"graph_digest": task["graph_digest"]})
            return {"task_id": task_id, "generation": generation, "nodes": graph}

    def claim(self, tenant_id, task_id, node_id, claim_id, reserve_units, lease_seconds):
        identity(claim_id, "claim_id")
        strict_int(reserve_units, "reserve_units")
        strict_int(lease_seconds, "lease_seconds", 1, 86400)
        parameters = {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "node_id": node_id,
            "reserve_units": reserve_units,
            "lease_seconds": lease_seconds,
        }
        key = digest_json([tenant_id, claim_id])
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            try:
                old = self._get(c, "claims", key, tenant_id)
            except NotFound:
                old = None
            if old:
                if old["parameters"] != parameters:
                    raise Conflict("claim identity binds changed parameters")
                self._owner(c, guard, old["grant"]["owner"])
                return old["grant"]
            self._eligible(c, guard, task, task["generation"])
            node = self._get(c, "nodes", task_id + ":" + node_id, tenant_id, task_id)
            self._dependencies(c, task, node)
            if node["status"] == "completed":
                raise Fenced("node already completed")
            previous = [
                a for a in self._list(c, "attempts", tenant_id, task_id) if a["owner"]["node_id"] == node_id
            ]
            if len(previous) >= task["contract"]["max_attempts"]:
                raise CapacityExceeded("node attempt limit exhausted")
            for attempt in previous:
                sandbox = self._get(c, "sandboxes", attempt["sandbox_id"], tenant_id, task_id)
                if sandbox["status"] != "retired":
                    raise CapacityExceeded("previous environment retirement unconfirmed")
                if any(
                    d["effect_state"] in ("in_flight", "unknown")
                    for d in self._list(c, "dispatches", tenant_id, task_id)
                    if d["attempt_id"] == attempt["attempt_id"]
                ):
                    raise Fenced("previous operation requires reconciliation")
            all_slots = self._list(c, "sandboxes")
            occupied = [s for s in all_slots if s["status"] != "retired"]
            if (
                len(occupied) >= guard["service_slot_limit"]
                or sum(s["tenant_id"] == tenant_id for s in occupied) >= guard["tenant_slot_limit"]
                or sum(s["task_id"] == task_id and s.get("kind", "patch") == "patch" for s in occupied)
                >= task["contract"]["patch_slot_limit"]
            ):
                raise CapacityExceeded("physical slot limit exhausted")
            self._reserve(c, guard, task, reserve_units)
            attempt_id, sandbox_id, reservation_id = _id(), _id(), _id()
            owner = {
                "service_incarnation": guard["service_incarnation"],
                "tenant_id": tenant_id,
                "task_id": task_id,
                "generation": task["generation"],
                "node_id": node_id,
                "node_epoch": node["node_epoch"] + 1,
                "attempt_id": attempt_id,
            }
            grant = {
                **owner,
                "owner": owner,
                "sandbox_id": sandbox_id,
                "reservation_id": reservation_id,
                "lease_until": self._now(c) + lease_seconds,
                "allowance_remaining": reserve_units,
            }
            attempt = {**grant, "status": "running", "claim_id": claim_id, "reserved_units": reserve_units}
            self._eligible(c, guard, task, task["generation"])
            self._save(c, "attempts", attempt_id, tenant_id, task_id, attempt, new=True)
            self._save(
                c,
                "sandboxes",
                sandbox_id,
                tenant_id,
                task_id,
                {
                    "sandbox_id": sandbox_id,
                    "attempt_id": attempt_id,
                    "tenant_id": tenant_id,
                    "task_id": task_id,
                    "kind": "patch",
                    "status": "reserved",
                    "retirement_evidence": None,
                },
                new=True,
            )
            node.update(node_epoch=owner["node_epoch"], attempt_id=attempt_id, status="running")
            self._save(c, "nodes", task_id + ":" + node_id, tenant_id, task_id, node)
            self._save(
                c, "claims", key, tenant_id, task_id, {"parameters": parameters, "grant": grant}, new=True
            )
            self._event(c, guard, tenant_id, task_id, "attempt.claimed", grant)
            return grant

    def heartbeat(self, owner, lease_seconds):
        strict_int(lease_seconds, "lease_seconds", 1, 86400)
        with self._tx() as (c, guard):
            owner, task, node, attempt = self._owner(c, guard, owner)
            attempt["lease_until"] = min(self._now(c) + lease_seconds, task["contract"]["execution_deadline"])
            self._owner(c, guard, owner)
            self._save(c, "attempts", owner["attempt_id"], owner["tenant_id"], owner["task_id"], attempt)
            self._event(
                c,
                guard,
                owner["tenant_id"],
                owner["task_id"],
                "attempt.heartbeat",
                {"attempt_id": owner["attempt_id"], "lease_until": attempt["lease_until"]},
            )
            return {"owner": owner, "lease_until": attempt["lease_until"]}

    def begin_projected_dispatch(self, owner, action_id, dispatch_id, kind, input_digest, bound_units,
                                 *, projection_manifest, expected_frontier,
                                 expected_previous_projection_id, replay_only=False):
        from .recovery import validate_context_manifest
        if self.artifact_store is None:
            raise ValueError("projected dispatch requires configured artifact storage")
        manifest = freeze(projection_manifest)
        validated = validate_context_manifest(self.artifact_store, owner["tenant_id"], owner["task_id"], manifest)
        from .context import plan_context
        candidate = plan_context(validated["projection"]["constraints"], validated["source"]["messages"],
                                 validated["source"]["evidence"], binding=manifest["binding"],
                                 config=manifest["config"],
                                 protocol="nebius" if manifest["binding"]["adapter"]["provider"] == "nebius" else "anthropic")
        if canonical_bytes(candidate["projection"]) != canonical_bytes(validated["projection"]):
            raise ValueError("published projection does not match deterministic planner")
        if manifest["source_checkpoint"] is not None and manifest["context_schema"] != 2:
            from .recovery import restore_checkpoint
            restored = restore_checkpoint(self, self.artifact_store, owner["tenant_id"], owner["task_id"],
                                          manifest["source_checkpoint"])
            prior_context = restored.get("context")
            if (prior_context is None
                    or prior_context["acceptance"]["projection_id"] != manifest["restored_from_projection_id"]
                    or prior_context["acceptance"]["manifest"]["config"] != manifest["config"]
                    or prior_context["acceptance"]["manifest"]["binding"]["adapter"] != manifest["binding"]["adapter"]
                    or canonical_bytes(validated["source"]["messages"][:len(restored["messages"])]) != canonical_bytes(restored["messages"])
                    or canonical_bytes(validated["source"]["evidence"][:len(restored["evidence"])]) != canonical_bytes(restored["evidence"])):
                raise ValueError("projection source does not extend validated restore checkpoint")
        expected_kind = {"scripted": "model.scripted", "anthropic": "model.anthropic", "nebius": "model.nebius"}[
            manifest["binding"]["adapter"]["provider"]]
        if kind != expected_kind:
            raise Conflict("projected dispatch kind differs from adapter")
        expected_bound = 0
        if expected_kind != "model.scripted":
            from .billing import ProviderEnvelope
            contract = validated["projection"]["constraints"]
            expected_bound = ProviderEnvelope(contract["rate_snapshot"], contract["model"]).bound_units
        if bound_units != expected_bound:
            raise Conflict("projected dispatch reservation differs from frozen envelope")
        if (manifest["request_digest"] != input_digest
                or manifest["binding"]["owner"] != owner
                or manifest["binding"]["source_frontier"] != expected_frontier
                or manifest["binding"]["expected_previous_projection_id"] != expected_previous_projection_id):
            raise Conflict("projection dispatch identity mismatch")
        skills_fingerprint = None
        if manifest["context_schema"] == 2:
            from .skill_disclosure import preflight_model
            skills_fingerprint = preflight_model(self, self.artifact_store, owner, manifest, validated, dispatch_id)
        return self._begin_dispatch(owner, action_id, dispatch_id, kind, input_digest, bound_units,
                                    context_manifest=manifest, skills_fingerprint=skills_fingerprint,
                                    replay_only=replay_only)

    def begin_dispatch(self, owner, action_id, dispatch_id, kind, input_digest, bound_units):
        return self._begin_dispatch(owner, action_id, dispatch_id, kind, input_digest, bound_units)

    def _skill_records(self, c, owner):
        from .skills import SkillError
        table = TABLES["dispatches"]
        rows = c.execute(sa.select(table.c.data).where(
            table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
            table.c.data["attempt_id"].as_string() == owner["attempt_id"]
        ).order_by(table.c.id).limit(65)).scalars().all()
        if len(rows) > 64:
            raise SkillError("bounds_exceeded")
        dispatches = [freeze(row) for row in rows]
        dispatch_ids = set()
        receipts, seen = [], set()
        for dispatch in dispatches:
            if (not isinstance(dispatch, dict) or dispatch.get("owner") != owner
                    or dispatch.get("attempt_id") != owner["attempt_id"]
                    or dispatch.get("tenant_id") != owner["tenant_id"]
                    or dispatch.get("task_id") != owner["task_id"]
                    or dispatch.get("dispatch_id") in dispatch_ids):
                raise Conflict("skill evidence record scope or identity mismatch")
            identity(dispatch["dispatch_id"], "dispatch_id")
            dispatch_ids.add(dispatch["dispatch_id"])
            receipt_id = dispatch.get("receipt_id")
            if receipt_id is not None and receipt_id not in seen:
                if len(dispatches) + len(receipts) >= 64:
                    raise SkillError("bounds_exceeded")
                identity(receipt_id, "receipt_id")
                receipt = self._get(c, "receipts", digest_json([owner["tenant_id"], receipt_id]),
                                    owner["tenant_id"], owner["task_id"])
                if not isinstance(receipt, dict) or receipt.get("receipt_id") != receipt_id:
                    raise Conflict("skill receipt identity mismatch")
                receipts.append(receipt)
                seen.add(receipt_id)
            if receipt_id is not None:
                receipt = next(r for r in receipts if r["receipt_id"] == receipt_id)
                expected = {key: dispatch[key] for key in
                            ("dispatch_id", "receipt_id", "effect_state", "actual_units", "result_ref")}
                if canonical_bytes(receipt) != canonical_bytes(expected):
                    raise Conflict("skill evidence receipt differs from dispatch")
        return dispatches, receipts

    def read_skill_records(self, owner):
        owner = validate_owner(owner)
        with self._read() as c:
            attempt = self._get(c, "attempts", owner["attempt_id"], owner["tenant_id"], owner["task_id"])
            if attempt["owner"] != owner:
                raise Conflict("skill evidence owner mismatch")
            task = self._task(c, owner["tenant_id"], owner["task_id"])
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            dispatches, receipts = self._skill_records(c, owner)
            return freeze({"owner": owner, "contract": task["contract"],
                           "frontier": {"service_incarnation": guard["service_incarnation"],
                                        "sequence": task["event_sequence"]},
                           "dispatches": dispatches, "receipts": receipts})

    def _skill_proof(self, c, owner, source_checkpoint=None, *, checkpoint_read=False):
        """Collect bounded original rows, with one shared provenance-record budget."""
        from .skills import SkillError
        task = self._task(c, owner["tenant_id"], owner["task_id"])
        guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
        dispatches, receipts, checkpoints, attempts, frontiers = {}, {}, {}, {}, {}
        visited = set()

        def add(kind, key, value, target):
            scoped = (kind, owner["tenant_id"], owner["task_id"], key)
            if scoped not in visited:
                if len(visited) >= 64:
                    raise SkillError("bounds_exceeded")
                visited.add(scoped)
                target[key] = freeze(value)

        def attempt_rows(record_owner):
            key = record_owner["attempt_id"]
            if key in attempts:
                if attempts[key]["owner"] != record_owner:
                    raise Conflict("skill proof owner mismatch")
                return
            attempt = self._get(c, "attempts", key, owner["tenant_id"], owner["task_id"])
            if (attempt["owner"] != record_owner or record_owner["generation"] != task["generation"]
                    or record_owner["tenant_id"] != owner["tenant_id"]
                    or record_owner["task_id"] != owner["task_id"]):
                raise Conflict("skill proof attempt scope or generation mismatch")
            attempts[key] = freeze(attempt)
            rows, original_receipts = self._skill_records(c, record_owner)
            frontiers[key] = sorted(d["dispatch_id"] for d in rows)
            for row in rows:
                add("dispatch", row["dispatch_id"], row, dispatches)
            for row in original_receipts:
                add("receipt", row["receipt_id"], row, receipts)

        attempt_rows(owner)
        current = [d for d in dispatches.values() if d["owner"] == owner
                   and d.get("context_acceptance", {}).get("context_schema") == 2]
        seeds = {d["context_acceptance"]["manifest"]["source_checkpoint"] for d in current}
        if len(seeds) > 1 or (not checkpoint_read and seeds and source_checkpoint is not None and seeds != {source_checkpoint}):
            raise Conflict("skill proof seed changed within attempt")
        if source_checkpoint is None and seeds:
            source_checkpoint = next(iter(seeds))
        seed = source_checkpoint
        ancestors = set()
        while seed is not None:
            digest(seed, "source checkpoint")
            if seed in ancestors:
                raise Conflict("cyclic skills checkpoint provenance")
            ancestors.add(seed)
            row = self._get(c, "checkpoints", seed, owner["tenant_id"], owner["task_id"])
            if (row.get("checkpoint_id") != seed or row.get("contract") != task["contract"]
                    or row.get("owner", {}).get("generation") != task["generation"]):
                raise Conflict("skills checkpoint scope or contract mismatch")
            add("checkpoint", seed, row, checkpoints)
            attempt_rows(row["owner"])
            manifest = row["manifest"]
            if manifest.get("schema") != 3 or type(manifest.get("schema")) is not int:
                raise ValueError("accepted skills require a typed skills checkpoint")
            from .recovery import _closed, _CONTEXT_CHECKPOINT_KEYS, _CONTEXT_MANIFEST_KEYS
            _closed(manifest, {"artifact_ref", "workspace_ref", "provider_artifacts", "next_turn",
                               "completion_proposed", "schema", "kind", "context", "skills_after_turn"},
                    "skills checkpoint manifest")
            if manifest["kind"] != "harness_skills_v1":
                raise ValueError("unknown skills checkpoint kind")
            _closed(manifest["context"], _CONTEXT_CHECKPOINT_KEYS, "checkpoint context")
            _closed(manifest["context"]["acceptance"],
                    {"context_schema", "projection_id", "manifest", "accepted_sequence"}, "context acceptance")
            _closed(manifest["context"]["acceptance"]["manifest"],
                    _CONTEXT_MANIFEST_KEYS | {"skills_state_ref", "skills_state_digest", "prompt_digest"},
                    "accepted skills context manifest")
            seed = manifest["context"]["acceptance"]["manifest"]["source_checkpoint"]
        values = {"owner": owner, "contract": task["contract"], "generation": task["generation"],
                  "frontier": {"service_incarnation": guard["service_incarnation"], "sequence": task["event_sequence"]},
                  "source_checkpoint": source_checkpoint,
                  "dispatches": sorted(dispatches.values(), key=lambda d: d["dispatch_id"]),
                  "receipts": sorted(receipts.values(), key=lambda r: r["receipt_id"]),
                  "checkpoints": sorted(checkpoints.values(), key=lambda k: k["checkpoint_id"]),
                  "attempts": attempts, "attempt_frontiers": frontiers, "record_count": len(visited)}
        values["fingerprint"] = digest_json(values)
        return freeze(values)

    def read_skill_proof(self, owner, *, source_checkpoint=None):
        owner = validate_owner(owner)
        with self._read() as c:
            return self._skill_proof(c, owner, source_checkpoint)

    def read_skills_checkpoint(self, tenant_id, task_id, checkpoint_id):
        digest(checkpoint_id, "checkpoint id")
        with self._read() as c:
            row = self._get(c, "checkpoints", checkpoint_id, tenant_id, task_id)
            return self._skill_proof(c, row["owner"], checkpoint_id, checkpoint_read=True)

    def has_skills_acceptance(self, owner):
        owner = validate_owner(owner)
        table = TABLES["dispatches"]
        with self._read() as c:
            return c.execute(sa.select(table.c.id).where(
                table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
                table.c.data["attempt_id"].as_string() == owner["attempt_id"],
                table.c.data["context_acceptance"]["context_schema"].as_integer() == 2).limit(1)).first() is not None

    def begin_skill_dispatch(self, owner, action_id, dispatch_id, call_digest, skill_call, expected_frontier,
                             *, replay_only=False):
        from .skill_runtime import validate_skill_call
        metadata = validate_skill_call(skill_call)
        digest(call_digest, "call_digest")
        records = self.read_skill_records(owner)
        source = next((d for d in records["dispatches"]
                       if d["dispatch_id"] == metadata["source_model_dispatch_id"]), None)
        skills_fingerprint = None
        if source is not None and source.get("context_acceptance", {}).get("context_schema") == 2:
            from .skill_disclosure import preflight_skill
            skills_fingerprint = preflight_skill(self, self.artifact_store, owner, action_id, dispatch_id,
                                                 call_digest, metadata)
        return self._begin_dispatch(owner, action_id, dispatch_id,
            "load_skill" if metadata["operation"] == "load" else "read_skill_resource",
            digest_json({"call_digest": call_digest, "skill_call": metadata}), 0,
            skill_call=metadata, skill_frontier=expected_frontier, skills_fingerprint=skills_fingerprint,
            replay_only=replay_only)

    def _begin_dispatch(self, owner, action_id, dispatch_id, kind, input_digest, bound_units,
                        *, context_manifest=None, context_retrieval=None, skill_call=None, skill_frontier=None,
                        skills_fingerprint=None, replay_only=False):
        if skill_call is not None:
            from .skill_runtime import validate_skill_call
            skill_call = validate_skill_call(skill_call)
        identity(action_id, "action_id")
        identity(dispatch_id, "dispatch_id")
        identity(kind, "kind")
        digest(input_digest, "input_digest")
        strict_int(bound_units, "bound_units")
        owner = validate_owner(owner)
        parameters = {
            "owner": owner,
            "action_id": action_id,
            "dispatch_id": dispatch_id,
            "kind": kind,
            "input_digest": input_digest,
            "bound_units": bound_units,
        }
        with self._tx() as (c, guard):
            owner, task, node, attempt = self._owner(c, guard, owner)
            try:
                old = self._get(c, "dispatches", dispatch_id, owner["tenant_id"], owner["task_id"])
            except NotFound:
                old = None
            if old:
                if (old["parameters"] != parameters
                        or (canonical_bytes(old.get("context_acceptance", {}).get("manifest")) != canonical_bytes(context_manifest))
                        or canonical_bytes(old.get("context_retrieval")) != canonical_bytes(context_retrieval)
                        or canonical_bytes(old.get("skill_call")) != canonical_bytes(skill_call)):
                    raise Conflict("dispatch ID binds a different intent")
                return {**old, "duplicate": True}
            if replay_only:
                raise Conflict("known replay lacks original dispatch; reconciliation required")
            if skill_call is not None or skills_fingerprint is not None:
                table = TABLES["dispatches"]
                action_records = c.execute(sa.select(table.c.data).where(
                    table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
                    table.c.data["action_id"].as_string() == action_id).limit(1)).scalars().all()
            else:
                action_records = self._list(c, "dispatches", owner["tenant_id"], owner["task_id"])
            for old in action_records:
                if old["action_id"] == action_id:
                    raise Conflict(
                        "action already has a dispatch; reconcile its receipt before choosing another action"
                    )
            acceptance = None
            if skills_fingerprint is not None:
                from .skill_disclosure import records_fingerprint
                proof = self._skill_proof(c, owner, skills_fingerprint["source_checkpoint"])
                records = [d for d in proof["dispatches"] if d["owner"] == owner]
                receipts = proof["receipts"]
                if proof["record_count"] + 2 > 64:
                    from .skills import SkillError
                    raise SkillError("bounds_exceeded")
                if (records_fingerprint(proof) != skills_fingerprint
                        or not {"load_skill", "read_skill_resource"} <= set(task["contract"]["capabilities"])):
                    raise Fenced("skills evidence changed or exceeds admission bound")
            if skill_call is not None:
                expected_kind = "load_skill" if skill_call["operation"] == "load" else "read_skill_resource"
                if (kind != expected_kind or bound_units != 0 or context_manifest is not None
                        or context_retrieval is not None
                        or not {"load_skill", "read_skill_resource"} <= set(task["contract"]["capabilities"])):
                    raise Conflict("invalid skill intent or capabilities")
                records, receipts = self._skill_records(c, owner)
                if len(records) + len(receipts) + 2 > 64:
                    from .skills import SkillError
                    raise SkillError("bounds_exceeded")
                if any(d["effect_state"] in {"in_flight", "unknown"} for d in records):
                    raise Conflict("unresolved effects block new skill intent")
                if canonical_bytes(skill_frontier) != canonical_bytes({
                        "service_incarnation": guard["service_incarnation"], "sequence": task["event_sequence"]}):
                    raise Fenced("skill source frontier is stale")
                accepted = [d for d in records if "context_acceptance" in d]
                latest = max(accepted, key=lambda d: d["context_acceptance"]["accepted_sequence"]) if accepted else None
                if skills_fingerprint is not None:
                    if (latest is None or latest["dispatch_id"] != skill_call["source_model_dispatch_id"]
                            or latest["context_acceptance"]["context_schema"] != 2
                            or latest["context_acceptance"]["projection_id"] != skill_call["source_projection_id"]
                            or latest["context_acceptance"]["accepted_sequence"] != skill_call["source_accepted_sequence"]
                            or latest["effect_state"] != "succeeded" or latest["billing_state"] != "settled"):
                        raise Conflict("skills require latest accepted successful source")
                else:
                    from .skill_runtime import validate_source_record
                    validate_source_record(latest, receipts, owner, skill_call, task["contract"])
            if context_retrieval is not None:
                if kind != "read_context_artifact" or bound_units != 0:
                    raise Conflict("invalid context retrieval intent")
                accepted = [d for d in self._list(c, "dispatches", owner["tenant_id"], owner["task_id"])
                            if d["attempt_id"] == owner["attempt_id"] and "context_acceptance" in d]
                latest = max(accepted, key=lambda d: d["context_acceptance"]["accepted_sequence"]) if accepted else None
                if (latest is None or latest["context_acceptance"]["projection_id"] != context_retrieval["projection_id"]
                        or latest["context_acceptance"]["accepted_sequence"] != context_retrieval["accepted_sequence"]
                        or latest["dispatch_id"] != context_retrieval["model_dispatch_id"]
                        or latest["effect_state"] != "succeeded" or not latest["result_ref"]
                        or latest["result_ref"].get("content_type") == "application/vnd.coding-agent.provider-transport-error+json"):
                    raise Conflict("retrieval requires latest accepted successful model response")
            if context_manifest is not None:
                binding = context_manifest["binding"]
                if (binding["contract_digest"] != digest_json(task["contract"])
                        or binding["generation"] != task["generation"]
                        or binding["source_frontier"] != {
                            "service_incarnation": guard["service_incarnation"],
                            "sequence": task["event_sequence"]}):
                    raise Fenced("context source frontier or contract is stale")
                previous = records if skills_fingerprint is not None else [
                    d for d in self._list(c, "dispatches", owner["tenant_id"], owner["task_id"])
                    if d["attempt_id"] == owner["attempt_id"]]
                if any(d["effect_state"] in {"in_flight", "unknown"} for d in previous):
                    raise Conflict("unresolved effects block new projected dispatch")
                accepted = [d["context_acceptance"] for d in previous if "context_acceptance" in d]
                latest = max(accepted, key=lambda a: a["accepted_sequence"]) if accepted else None
                if binding["expected_previous_projection_id"] != (latest["projection_id"] if latest else None):
                    raise Fenced("context previous projection is stale")
                if context_manifest["source_checkpoint"] is not None:
                    source_checkpoint = self._get(c, "checkpoints", context_manifest["source_checkpoint"],
                                                  owner["tenant_id"], owner["task_id"])
                    checkpoint_context = source_checkpoint["manifest"].get("context")
                    if (not checkpoint_context or checkpoint_context["acceptance"]["projection_id"]
                            != context_manifest["restored_from_projection_id"]
                            or source_checkpoint["contract"] != task["contract"]
                            or source_checkpoint["owner"]["generation"] != owner["generation"]):
                        raise Fenced("projection restore provenance mismatch")
                projection_id = digest_json(context_manifest)
                event = self._event(c, guard, owner["tenant_id"], owner["task_id"],
                                    "context.accepted", {"projection_id": projection_id,
                                    "accepted_sequence": task["event_sequence"] + 1,
                                    "dispatch_id": dispatch_id})
                acceptance = {"context_schema": context_manifest["context_schema"], "projection_id": projection_id,
                              "manifest": context_manifest, "accepted_sequence": event["sequence"]}
            if bound_units > attempt["allowance_remaining"]:
                raise BudgetExceeded("dispatch bound exceeds attempt allowance")
            attempt["allowance_remaining"] -= bound_units
            self._owner(c, guard, owner)
            self._save(c, "attempts", owner["attempt_id"], owner["tenant_id"], owner["task_id"], attempt)
            dispatch = {
                **parameters,
                "parameters": parameters,
                "tenant_id": owner["tenant_id"],
                "task_id": owner["task_id"],
                "attempt_id": owner["attempt_id"],
                "effect_state": "in_flight",
                "billing_state": "reserved",
                "actual_units": None,
                "result_ref": None,
                "receipt_id": None,
                "created_at": self._now(c),
            }
            if acceptance is not None:
                dispatch["context_acceptance"] = acceptance
            if context_retrieval is not None:
                dispatch["context_retrieval"] = freeze(context_retrieval)
            if skill_call is not None:
                dispatch["skill_call"] = freeze(skill_call)
            self._save(c, "dispatches", dispatch_id, owner["tenant_id"], owner["task_id"], dispatch, new=True)
            self._event(c, guard, owner["tenant_id"], owner["task_id"], "dispatch.intent", parameters)
            self._command(c, guard, task, "dispatch", {"dispatch_id": dispatch_id, "action_id": action_id})
            return {**dispatch, "duplicate": False}

    def finish_dispatch(
        self, tenant_id, dispatch_id, receipt_id, effect_state, actual_units=None, result_ref=None
    ):
        identity(receipt_id, "receipt_id")
        if effect_state not in ("succeeded", "failed_known", "unknown", "not_dispatched"):
            raise ValueError("invalid terminal effect knowledge")
        if actual_units is not None:
            strict_int(actual_units, "actual_units")
        with self.engine.connect() as c:
            pre = self._get(c, "dispatches", dispatch_id, tenant_id)
        self._references(tenant_id, pre["task_id"], result_ref)
        parameters = {
            "dispatch_id": dispatch_id,
            "receipt_id": receipt_id,
            "effect_state": effect_state,
            "actual_units": actual_units,
            "result_ref": freeze(result_ref),
        }
        violation = False
        with self._tx() as (c, guard):
            dispatch = self._get(c, "dispatches", dispatch_id, tenant_id)
            task_id = dispatch["task_id"]
            receipt_key = digest_json([tenant_id, receipt_id])
            try:
                old = self._get(c, "receipts", receipt_key, tenant_id)
            except NotFound:
                old = None
            if old:
                if old != parameters:
                    raise Conflict("receipt identity binds changed content")
                return dispatch
            if (
                dispatch["result_ref"] is not None
                and result_ref is not None
                and dispatch["result_ref"] != freeze(result_ref)
            ):
                raise Conflict("dispatch effect evidence is already bound to different immutable content")
            already_settled = dispatch["billing_state"] == "settled"
            if already_settled:
                if actual_units is not None and actual_units != dispatch["actual_units"]:
                    raise Conflict("dispatch charge already settled with different actual usage")
                if dispatch["effect_state"] != "unknown" or effect_state == "unknown":
                    raise Conflict("dispatch already settled; only unresolved effect reconciliation allowed")
            if (
                dispatch["effect_state"] in ("succeeded", "failed_known", "not_dispatched")
                and dispatch["effect_state"] != effect_state
            ):
                raise Conflict("known effect cannot be downgraded or changed")
            if effect_state == "not_dispatched" and (
                actual_units not in (None, 0) or already_settled and dispatch["actual_units"] != 0
            ):
                raise Conflict("not-dispatched receipt cannot charge usage")
            dispatch.update(
                effect_state=effect_state,
                result_ref=dispatch["result_ref"] if result_ref is None else freeze(result_ref),
                receipt_id=receipt_id,
                actual_units=dispatch["actual_units"] if already_settled else actual_units,
                finished_at=self._now(c),
                billing_state="settled"
                if already_settled or actual_units is not None
                else "liability_unknown",
            )
            if not already_settled and actual_units is not None and actual_units > dispatch["bound_units"]:
                violation = True
                dispatch["bound_violation"] = True
                guard.update(
                    accept_new_tasks=False,
                    execution_enabled=False,
                    quarantined=True,
                    containment_reason="usage exceeded enforceable dispatch bound",
                )
                c.execute(authority.update().where(authority.c.id == 1).values(data=guard))
            self._save(c, "dispatches", dispatch_id, tenant_id, task_id, dispatch)
            self._save(c, "receipts", receipt_key, tenant_id, task_id, parameters, new=True)
            self._event(
                c,
                guard,
                tenant_id,
                task_id,
                "dispatch.bound_violation" if violation else "dispatch.receipt",
                parameters,
            )
        if violation:
            raise BudgetExceeded(
                "actual usage exceeded dispatch bound; usage retained and service quarantined"
            )
        return dispatch

    def _manifest(self, task, manifest):
        manifest = freeze(manifest)
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        digest(manifest.get("tree_digest"), "tree_digest")
        if manifest.get("base_revision") != task["contract"]["base_revision"]:
            raise Conflict("candidate base revision differs from frozen contract")
        if (
            manifest.get("environment_digest", task["contract"]["environment_digest"])
            != task["contract"]["environment_digest"]
        ):
            raise Conflict("candidate environment mismatch")
        if "manifest_digest" in manifest:
            unsigned = {
                k: v
                for k, v in manifest.items()
                if k not in ("manifest_digest", "artifact_ref", "candidate_id")
            }
            if manifest["manifest_digest"] != digest_json(unsigned):
                raise Conflict("candidate manifest digest mismatch")
        if "files" not in manifest or "base_files" not in manifest:
            raise Unsupported(
                "reference candidates require reconstructible exact text files and cryptographically bound base_files"
            )
        for field in ("files", "base_files"):
            files = manifest[field]
            if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
                raise ValueError("reference tree supports text files only")
            for path in files:
                if (
                    not isinstance(path, str)
                    or path.startswith(("/", "\\"))
                    or "\\" in path
                    or any(part in ("", ".", "..", ".git") for part in path.split("/"))
                ):
                    raise Conflict("unsafe tree path")
            expected = manifest["tree_digest"] if field == "files" else task["contract"]["base_revision"]
            if digest_json({"format": "sha256-text-tree-v1", "files": files}) != expected:
                raise Conflict("candidate tree/base digest mismatch")
        base, files = manifest["base_files"], manifest["files"]
        changed = sorted(path for path in set(base) | set(files) if base.get(path) != files.get(path))
        if manifest.get("changed_paths") != changed:
            raise Conflict("candidate changed_paths does not identify the exact delta")
        return manifest

    def _prepare_manifest(self, tenant_id, task_id, manifest):
        manifest = freeze(manifest)
        self._references(tenant_id, task_id, manifest)
        if isinstance(manifest, dict) and "artifact_ref" in manifest:
            ref = manifest["artifact_ref"]
            if not isinstance(ref, dict) or not {"tenant_id", "task_id", "digest", "size"} <= set(ref):
                raise ValueError("manifest artifact_ref must be a scoped immutable reference")
            raw = self.artifact_store.get(tenant_id, task_id, ref["digest"])
            expected = {k: v for k, v in manifest.items() if k not in ("artifact_ref", "candidate_id")}
            if raw != canonical_bytes(expected):
                raise Conflict("manifest artifact bytes do not match submitted manifest")
        return manifest

    def accept_candidate(self, owner, manifest):
        owner = validate_owner(owner)
        manifest = freeze(manifest)
        if not isinstance(manifest, dict):
            raise ValueError("candidate manifest must be an object")
        # Receipt replay is a read: it never renews revoked worker authority.
        with self._read() as c:
            prior = [
                record
                for record in self._list(c, "candidates", owner["tenant_id"], owner["task_id"])
                if record.get("kind") == "worker" and record.get("owner") == owner
            ]
            if prior:
                if prior[0]["manifest"] != manifest:
                    raise Conflict("candidate owner already binds a different accepted manifest")
                return prior[0]
        manifest = self._prepare_manifest(owner["tenant_id"], owner["task_id"], manifest)
        with self._tx() as (c, guard):
            # Recheck after acquiring authority: concurrent ack-loss retries converge.
            prior = [
                record
                for record in self._list(c, "candidates", owner["tenant_id"], owner["task_id"])
                if record.get("kind") == "worker" and record.get("owner") == owner
            ]
            if prior:
                if prior[0]["manifest"] != manifest:
                    raise Conflict("candidate owner already binds a different accepted manifest")
                return prior[0]
            owner, task, node, attempt = self._owner(c, guard, owner)
            manifest = self._manifest(task, manifest)
            if "allowed_paths" in node and not set(manifest.get("changed_paths", [])) <= set(
                node["allowed_paths"]
            ):
                raise Fenced("candidate changes paths outside its node contract")
            if "requirements" in manifest and manifest["requirements"] != task["contract"]["requirements"]:
                raise Conflict("candidate requirement version mismatch")
            dependency_versions = {
                dep: self._get(
                    c, "nodes", owner["task_id"] + ":" + dep, owner["tenant_id"], owner["task_id"]
                )["candidate_id"]
                for dep in node["dependencies"]
            }
            if "inputs" in manifest and manifest["inputs"] != list(dependency_versions.values()):
                raise Fenced("candidate dependency input frontier mismatch")
            if "dependency_versions" in manifest and manifest["dependency_versions"] != dependency_versions:
                raise Fenced("candidate dependency version mismatch")
            if "owner" in manifest and validate_owner(manifest["owner"]) != owner:
                raise Fenced("manifest producer mismatch")
            if any(
                d["effect_state"] in ("in_flight", "unknown")
                for d in self._list(c, "dispatches", owner["tenant_id"], owner["task_id"])
                if d["attempt_id"] == owner["attempt_id"]
            ):
                raise Fenced("candidate has unresolved effects")
            candidate_id = manifest.get("candidate_id") or digest_json([owner, manifest])
            identity(candidate_id, "candidate_id")
            candidate = {
                "candidate_id": candidate_id,
                "tenant_id": owner["tenant_id"],
                "task_id": owner["task_id"],
                "generation": owner["generation"],
                "owner": owner,
                "manifest": manifest,
                "tree_digest": manifest["tree_digest"],
                "contract_digest": task["contract_digest"],
                "kind": "worker",
                "dependency_versions": dependency_versions,
                "accepted_at": self._now(c),
            }
            self._owner(c, guard, owner)
            self._save(
                c, "candidates", candidate_id, owner["tenant_id"], owner["task_id"], candidate, new=True
            )
            node.update(status="completed", candidate_id=candidate_id)
            attempt["status"] = "completed"
            self._save(
                c,
                "nodes",
                owner["task_id"] + ":" + owner["node_id"],
                owner["tenant_id"],
                owner["task_id"],
                node,
            )
            self._save(c, "attempts", owner["attempt_id"], owner["tenant_id"], owner["task_id"], attempt)
            self._event(
                c,
                guard,
                owner["tenant_id"],
                owner["task_id"],
                "candidate.accepted",
                {"candidate_id": candidate_id, "tree_digest": candidate["tree_digest"]},
            )
            self._command(c, guard, task, "candidate_ready", {"candidate_id": candidate_id})
            return candidate

    def cancel(self, tenant_id, task_id, request_id):
        identity(request_id, "cancel request")
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            cancellations = task.setdefault("cancellations", [])
            if request_id in cancellations:
                return task
            cancellations.append(request_id)
            if task["execution_state"] != "cancelled":
                prior_generation = task["generation"]
                task["generation"] += 1
                task.update(
                    execution_state="cancelled",
                    review_state="withdrawn" if task["review_state"] == "pending" else task["review_state"],
                    cancel_requested_at=self._now(c),
                    authority_revoked_at=self._now(c),
                )
                for attempt in self._list(c, "attempts", tenant_id, task_id):
                    if attempt["status"] == "running":
                        attempt["status"] = "revoked"
                        self._save(c, "attempts", attempt["attempt_id"], tenant_id, task_id, attempt)
                for sandbox in self._list(c, "sandboxes", tenant_id, task_id):
                    if sandbox["status"] != "retired":
                        sandbox["status"] = "retirement_requested"
                        self._save(c, "sandboxes", sandbox["sandbox_id"], tenant_id, task_id, sandbox)
                        self._command(
                            c,
                            guard,
                            task,
                            "stop_sandbox",
                            {"sandbox_id": sandbox["sandbox_id"], "target_generation": prior_generation},
                        )
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(
                c,
                guard,
                tenant_id,
                task_id,
                "task.cancelled",
                {"request_id": request_id, "generation": task["generation"]},
            )
            return self._task(c, tenant_id, task_id)

    def _evidence(self, tenant_id, task_id, evidence_ref):
        if not isinstance(evidence_ref, dict) or not evidence_ref:
            raise ValueError("trusted observation evidence must be a nonempty object")
        self._references(tenant_id, task_id, evidence_ref)
        return freeze(evidence_ref)

    def read_environment_journal(self, tenant_id, sandbox_id):
        from .environment_recovery import validate_journal
        with self._read() as c:
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            if row["attempt_id"] is not None:
                owner = self._get(c, "attempts", row["attempt_id"], tenant_id, row["task_id"])["owner"]
                row = {**row, "generation": owner["generation"], "service_incarnation": owner["service_incarnation"]}
            if row.get("environment_journal") is not None:
                validate_journal(row["environment_journal"], sandbox_id, tenant_id, row["task_id"])
            return freeze(row)

    def _environment_controller(self, guard):
        if self.execution_incarnation != guard["service_incarnation"]:
            raise Fenced("environment cleanup requires current service incarnation")

    def assert_environment_cleanup(self, tenant_id, sandbox_id, intent_id):
        from .environment_recovery import validate_journal
        with self._read() as c:
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            self._environment_controller(guard)
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            journal = validate_journal(row.get("environment_journal"), sandbox_id, tenant_id, row["task_id"])
            if not any(i["intent_id"] == intent_id for i in journal["instances"]):
                raise Conflict("environment cleanup intent outside reservation")
            return freeze(row)

    def assert_environment_execution(self, tenant_id, sandbox_id, intent_id):
        from .environment_recovery import validate_journal
        with self._read() as c:
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            self._environment_controller(guard)
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            task = self._task(c, tenant_id, row["task_id"])
            journal = validate_journal(row.get("environment_journal"), sandbox_id, tenant_id, row["task_id"])
            self._eligible(c, guard, task, journal["source"]["generation"])
            if (row["status"] != "reserved" or journal["phase"] != "open"
                    or journal["source"]["service_incarnation"] != guard["service_incarnation"]):
                raise Fenced("environment execution revoked or cleanup requested")
            if row["attempt_id"] is not None:
                self._owner(c, guard, self._get(c, "attempts", row["attempt_id"], tenant_id, row["task_id"])["owner"])
            instance = next((i for i in journal["instances"] if i["intent_id"] == intent_id), None)
            if instance is None or instance["state"] not in {"create_intent", "bound"}:
                raise Fenced("environment instance has no execution authority")
            return freeze(instance)

    def begin_environment_instance(self, tenant_id, sandbox_id, *, source, backend, max_instances, ordinal, launch):
        from .environment_recovery import (validate_source, validate_backend, validate_launch, validate_journal,
                                           intent_identity, PROFILE)
        source, backend, launch = validate_source(source), validate_backend(backend), validate_launch(launch)
        strict_int(max_instances, "instance bound", 1, 32)
        strict_int(ordinal, "instance ordinal", 0, max_instances - 1)
        with self._read() as c:
            pre = self._get(c, "sandboxes", sandbox_id, tenant_id)
        prior_journal = pre.get("environment_journal")
        if prior_journal is not None:
            from .environment_recovery import validate_terminal_observations
            validate_journal(prior_journal, sandbox_id, tenant_id, pre["task_id"])
            validate_terminal_observations(self.artifact_store, tenant_id, pre["task_id"], prior_journal)
        with self._tx() as (c, guard):
            self._environment_controller(guard)
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            task_id = row["task_id"]
            task = self._task(c, tenant_id, task_id)
            self._eligible(c, guard, task, source["generation"])
            original_owner = self._get(c, "attempts", row["attempt_id"], tenant_id, task_id)["owner"] if row["attempt_id"] is not None else None
            row_generation = original_owner["generation"] if original_owner is not None else row["generation"]
            row_incarnation = original_owner["service_incarnation"] if original_owner is not None else row["service_incarnation"]
            if (source["generation"] != row_generation or source["service_incarnation"] != guard["service_incarnation"]
                    or row_incarnation != guard["service_incarnation"]
                    or source["grader_digest"] != task["contract"]["grader_digest"]
                    or source["environment_digest"] != task["contract"]["environment_digest"]):
                raise Fenced("environment source differs from frozen reservation authority")
            if row["attempt_id"] is not None:
                self._owner(c, guard, self._get(c, "attempts", row["attempt_id"], tenant_id, task_id)["owner"])
            journal = row.get("environment_journal")
            if journal is None:
                journal = {"schema": 1, "profile": PROFILE, "revision": 1, "phase": "open", "source": source,
                           "backend": backend, "max_instances": max_instances, "instances": []}
            else:
                journal = validate_journal(journal, sandbox_id, tenant_id, task_id)
                if journal["source"] != source or journal["backend"] != backend or journal["max_instances"] != max_instances:
                    raise Conflict("environment journal initialization identity changed")
            identifier = intent_identity(sandbox_id, ordinal, source, backend, launch)
            if ordinal < len(journal["instances"]):
                instance = journal["instances"][ordinal]
                if instance["intent_id"] != identifier or instance["launch"] != launch:
                    raise Conflict("environment ordinal binds changed create intent")
                return {"duplicate": True, "revision": journal["revision"], "instance": freeze(instance)}
            if canonical_bytes(row.get("environment_journal")) != canonical_bytes(prior_journal):
                raise Fenced("environment admission proof changed after artifact preflight")
            if (row["status"] != "reserved" or journal["phase"] != "open"
                    or ordinal != len(journal["instances"])
                    or any(i["state"] not in {"retired", "create_rejected"} for i in journal["instances"])):
                raise Conflict("environment instance admission blocked by cleanup or unresolved creation")
            instance = {"ordinal": ordinal, "intent_id": identifier, "name": "cam-sandbox-" + identifier[:48],
                        "creation_nonce": uuid.uuid4().hex, "launch": launch, "state": "create_intent",
                        "container_id": None, "create_observation_ref": None, "retirement_observation_ref": None}
            if row.get("environment_journal") is not None:
                journal["revision"] += 1
            journal["instances"].append(instance)
            row["environment_journal"] = validate_journal(journal, sandbox_id, tenant_id, task_id)
            self._eligible(c, guard, task, source["generation"])
            self._save(c, "sandboxes", sandbox_id, tenant_id, task_id, row)
            self._event(c, guard, tenant_id, task_id, "environment.instance_intent",
                        {"sandbox_id": sandbox_id, "revision": journal["revision"], "instance": instance,
                         "source": source, "backend": backend})
            return {"duplicate": False, "revision": journal["revision"], "instance": freeze(instance)}

    def _environment_observation(self, tenant_id, sandbox_id, intent_id, observation_ref, expected_revision, kind):
        from .environment_recovery import validate_journal, read_observation
        strict_int(expected_revision, "journal revision", 1)
        digest(intent_id, "environment intent")
        with self._read() as c:
            before = self._get(c, "sandboxes", sandbox_id, tenant_id)
        if self.artifact_store is None:
            raise ValueError("environment observations require artifact storage")
        value = read_observation(self.artifact_store, tenant_id, before["task_id"], observation_ref)
        if value["kind"] != kind:
            raise ValueError("environment observation operation mismatch")
        with self._tx() as (c, guard):
            self._environment_controller(guard)
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            task_id = row["task_id"]
            journal = validate_journal(row.get("environment_journal"), sandbox_id, tenant_id, task_id)
            instance = next((i for i in journal["instances"] if i["intent_id"] == intent_id), None)
            if instance is None:
                raise Conflict("environment intent outside reservation")
            if any(value[k] != expected for k, expected in {
                    "intent_id": instance["intent_id"], "ordinal": instance["ordinal"], "name": instance["name"],
                    "creation_nonce": instance["creation_nonce"], "backend": journal["backend"],
                    "launch_digest": digest_json(instance["launch"])}.items()):
                raise Conflict("environment observation ownership mismatch")
            key = "create_observation_ref" if kind == "create" else "retirement_observation_ref"
            if instance[key] == observation_ref:
                return {"duplicate": True, "revision": journal["revision"], "instance": freeze(instance)}
            if journal["revision"] != expected_revision:
                raise Fenced("environment observation revision changed")
            cid, state = value["container_id"], instance["state"]
            if instance["container_id"] is not None and instance["container_id"] != cid:
                raise Conflict("environment immutable container ID changed")
            if state in {"retired", "create_rejected"} or journal["phase"] == "retired":
                raise Conflict("environment terminal observation cannot change")
            if value["status"] == "bound":
                if state != "create_intent":
                    raise Conflict("environment binding already fixed")
                instance.update(state="bound", container_id=cid)
            elif value["status"] == "create_rejected":
                if state != "create_intent":
                    raise Conflict("environment create rejection after binding")
                instance["state"] = "create_rejected"
            elif value["status"] == "absent":
                if state != "bound" or cid != instance["container_id"]:
                    raise Conflict("unbound create absence cannot prove retirement")
                instance["state"] = "retired"
            elif value["status"] == "unresolved":
                if cid != instance["container_id"]:
                    raise Conflict("unresolved observation cannot invent a container binding")
            else:
                raise ValueError("unsupported environment observation transition")
            instance[key] = freeze(observation_ref)
            journal["revision"] += 1
            row["environment_journal"] = validate_journal(journal, sandbox_id, tenant_id, task_id)
            self._save(c, "sandboxes", sandbox_id, tenant_id, task_id, row)
            self._event(c, guard, tenant_id, task_id, "environment.instance_observed",
                        {"sandbox_id": sandbox_id, "intent_id": intent_id, "revision": journal["revision"],
                         "kind": kind, "status": value["status"], "observation_ref": observation_ref})
            return {"duplicate": False, "revision": journal["revision"], "instance": freeze(instance)}

    def bind_environment_instance(self, tenant_id, sandbox_id, intent_id, observation_ref, *, expected_revision):
        return self._environment_observation(tenant_id, sandbox_id, intent_id, observation_ref, expected_revision, "create")

    def record_environment_retirement(self, tenant_id, sandbox_id, intent_id, observation_ref, *, expected_revision):
        return self._environment_observation(tenant_id, sandbox_id, intent_id, observation_ref, expected_revision, "retirement")

    def request_environment_cleanup(self, tenant_id, sandbox_id):
        from .environment_recovery import validate_journal
        with self._tx() as (c, guard):
            self._environment_controller(guard)
            row = self._get(c, "sandboxes", sandbox_id, tenant_id)
            task_id = row["task_id"]
            journal = validate_journal(row.get("environment_journal"), sandbox_id, tenant_id, task_id)
            if journal["phase"] in {"cleanup_requested", "retired"}:
                return freeze(row)
            journal["phase"] = "cleanup_requested"
            journal["revision"] += 1
            row["environment_journal"] = validate_journal(journal, sandbox_id, tenant_id, task_id)
            self._save(c, "sandboxes", sandbox_id, tenant_id, task_id, row)
            self._event(c, guard, tenant_id, task_id, "environment.cleanup_requested",
                        {"sandbox_id": sandbox_id, "revision": journal["revision"]})
            return freeze(row)

    def retire_sandbox(self, tenant_id, sandbox_id, evidence_ref):
        with self.engine.connect() as c:
            pre = self._get(c, "sandboxes", sandbox_id, tenant_id)
        evidence = self._evidence(tenant_id, pre["task_id"], evidence_ref)
        if pre.get("environment_journal") is not None:
            from .environment_recovery import validate_journal, validate_terminal_observations
            journal = validate_journal(pre["environment_journal"], sandbox_id, tenant_id, pre["task_id"])
            validate_terminal_observations(self.artifact_store, tenant_id, pre["task_id"], journal)
        with self._tx() as (c, guard):
            sandbox = self._get(c, "sandboxes", sandbox_id, tenant_id)
            task_id = sandbox["task_id"]
            if (pre.get("environment_journal") is not None or sandbox.get("environment_journal") is not None) and (
                    canonical_bytes(sandbox.get("environment_journal")) != canonical_bytes(pre.get("environment_journal"))):
                raise Fenced("environment retirement proof changed after artifact preflight")
            if sandbox.get("environment_journal") is not None:
                from .environment_recovery import validate_journal, PROFILE
                self._environment_controller(guard)
                journal = validate_journal(sandbox["environment_journal"], sandbox_id, tenant_id, task_id)
                if sandbox["status"] == "retired":
                    if sandbox["retirement_evidence"] != evidence:
                        raise Conflict("retirement already observed with different evidence")
                    return sandbox
                expected = {"kind": PROFILE, "sandbox_id": sandbox_id, "journal_digest": digest_json(journal)}
                if (evidence != expected or journal["phase"] != "cleanup_requested"
                        or any(i["state"] not in {"retired", "create_rejected"} for i in journal["instances"])):
                    raise Conflict("journaled reservation requires complete trusted physical retirement")
                journal["phase"] = "retired"
                journal["revision"] += 1
                sandbox["environment_journal"] = validate_journal(journal, sandbox_id, tenant_id, task_id)
            if sandbox["status"] == "retired":
                if sandbox["retirement_evidence"] != evidence:
                    raise Conflict("retirement already observed with different evidence")
                return sandbox
            sandbox.update(status="retired", retirement_evidence=evidence, retired_at=self._now(c))
            self._save(c, "sandboxes", sandbox_id, tenant_id, task_id, sandbox)
            if sandbox["attempt_id"] is not None:
                attempt = self._get(c, "attempts", sandbox["attempt_id"], tenant_id, task_id)
                attempt["allowance_remaining"] = 0
                if attempt["status"] == "running":
                    attempt["status"] = "retired"
                self._save(c, "attempts", attempt["attempt_id"], tenant_id, task_id, attempt)
            if sandbox.get("environment_journal") is not None:
                table = TABLES["sandboxes"]
                quiescent = c.execute(sa.select(table.c.id).where(
                    table.c.tenant_id == tenant_id, table.c.task_id == task_id,
                    table.c.data["status"].as_string() != "retired").limit(1)).first() is None
            else:
                quiescent = all(s["status"] == "retired" for s in self._list(c, "sandboxes", tenant_id, task_id))
            if quiescent:
                task = self._task(c, tenant_id, task_id)
                task["quiescence_confirmed_at"] = self._now(c)
                self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(
                c,
                guard,
                tenant_id,
                task_id,
                "sandbox.retired",
                {"sandbox_id": sandbox_id, "evidence_ref": evidence},
            )
            return sandbox

    def _find_skill_checkpoint(self, c, owner, context, next_turn, completion_proposed):
        table = TABLES["checkpoints"]
        rows = c.execute(sa.select(table.c.data).where(
            table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
            table.c.data["owner"]["attempt_id"].as_string() == owner["attempt_id"],
            table.c.data["manifest"]["schema"].as_integer() == 3,
            table.c.data["manifest"]["context"]["dispatch_id"].as_string() == context["dispatch_id"],
            table.c.data["manifest"]["next_turn"].as_integer() == next_turn,
            table.c.data["manifest"]["completion_proposed"].as_boolean() == completion_proposed
        ).limit(2)).scalars().all()
        if len(rows) > 1:
            raise Conflict("ambiguous checkpoint cut")
        if rows and (rows[0]["owner"] != owner or rows[0]["manifest"]["context"] != context):
            raise Conflict("checkpoint cut binds different context")
        return freeze(rows[0]) if rows else None

    def find_skill_checkpoint(self, owner, context, next_turn, completion_proposed):
        with self._read() as c:
            return self._find_skill_checkpoint(c, validate_owner(owner), context, next_turn, completion_proposed)

    def read_skill_turn_checkpoint(self, owner, dispatch_id):
        owner = validate_owner(owner)
        table = TABLES["checkpoints"]
        with self._read() as c:
            rows = c.execute(sa.select(table.c.data).where(
                table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
                table.c.data["owner"]["attempt_id"].as_string() == owner["attempt_id"],
                table.c.data["manifest"]["schema"].as_integer() == 3,
                table.c.data["manifest"]["context"]["dispatch_id"].as_string() == dispatch_id
            ).limit(2)).scalars().all()
            if len(rows) > 1:
                raise Conflict("ambiguous checkpoint turn")
            return freeze(rows[0]) if rows else None

    def checkpoint(self, owner, manifest):
        owner = validate_owner(owner)
        self._references(owner["tenant_id"], owner["task_id"], manifest)
        if not isinstance(manifest, dict):
            raise ValueError("checkpoint must be an object")
        context = payload = None
        proof = existing = None
        skills = type(manifest.get("schema")) is int and manifest["schema"] == 3
        if skills:
            from .recovery import _closed, _CONTEXT_CHECKPOINT_KEYS, _CONTEXT_MANIFEST_KEYS
            _closed(manifest, {"artifact_ref", "workspace_ref", "provider_artifacts", "next_turn",
                               "completion_proposed", "schema", "kind", "context", "skills_after_turn"},
                    "skills checkpoint manifest")
            _closed(manifest["context"], _CONTEXT_CHECKPOINT_KEYS, "checkpoint context")
            _closed(manifest["context"]["acceptance"],
                    {"context_schema", "projection_id", "manifest", "accepted_sequence"}, "context acceptance")
            _closed(manifest["context"]["acceptance"]["manifest"],
                    _CONTEXT_MANIFEST_KEYS | {"skills_state_ref", "skills_state_digest", "prompt_digest"},
                    "accepted skills context manifest")
            if manifest["kind"] != "harness_skills_v1":
                raise ValueError("unknown skills checkpoint kind")
            from .skill_recovery import validate_skills_checkpoint, validate_seed_proof
            if self.artifact_store is None:
                raise ValueError("skills checkpoint requires artifact storage")
            seed = manifest["context"]["acceptance"]["manifest"]["source_checkpoint"]
            proof = self.read_skill_proof(owner, source_checkpoint=seed)
            validate_seed_proof(proof, self.artifact_store)
            existing = self.find_skill_checkpoint(owner, manifest["context"], manifest["next_turn"],
                                                  manifest["completion_proposed"])
            candidate = existing if existing is not None else {"owner": owner, "manifest": manifest}
            if existing is not None and existing["manifest"] != manifest:
                raise Conflict("checkpoint cut binds different bytes")
            validate_skills_checkpoint(proof, self.artifact_store, candidate, require_frontier=existing is None)
            if existing is None and proof["record_count"] + 1 > 64:
                from .skills import SkillError
                raise SkillError("bounds_exceeded")
        if any(k in manifest for k in ("kind", "context", "schema")):
            from .recovery import validate_context_checkpoint
            if self.artifact_store is None:
                raise ValueError("context checkpoint requires artifact storage")
            payload = self.artifact_store.get_json(owner["tenant_id"], owner["task_id"], manifest["artifact_ref"]["digest"])
            context = validate_context_checkpoint(self.artifact_store, owner["tenant_id"], owner["task_id"], manifest, payload)
        with self._tx() as (c, guard):
            owner, task, node, attempt = self._owner(c, guard, owner)
            table = TABLES["dispatches"]
            skills_present = c.execute(sa.select(table.c.id).where(
                table.c.tenant_id == owner["tenant_id"], table.c.task_id == owner["task_id"],
                table.c.data["attempt_id"].as_string() == owner["attempt_id"],
                table.c.data["context_acceptance"]["context_schema"].as_integer() == 2).limit(1)).first()
            if skills_present is not None and not skills:
                raise ValueError("skills acceptance requires a typed skills checkpoint")
            if skills and skills_present is None:
                raise ValueError("skills checkpoint requires accepted skills authority")
            if skills:
                if existing is not None:
                    durable = self._get(c, "checkpoints", existing["checkpoint_id"], owner["tenant_id"], owner["task_id"])
                    if durable != existing:
                        raise Fenced("accepted checkpoint changed")
                    return durable
                # ACK-loss and a racing identical acceptance converge without a new event.
                raced = self._find_skill_checkpoint(c, owner, manifest["context"], manifest["next_turn"],
                                                    manifest["completion_proposed"])
                if raced is not None:
                    if raced["manifest"] != manifest:
                        raise Conflict("checkpoint cut binds different bytes")
                    return raced
                checked = self._skill_proof(c, owner, proof["source_checkpoint"])
                if checked["fingerprint"] != proof["fingerprint"]:
                    raise Fenced("skills checkpoint proof or frontier changed")
                snapshot = {"dispatches": checked["dispatches"], "frontier": checked["frontier"],
                            "nodes": self._list(c, "nodes", owner["tenant_id"], owner["task_id"]),
                            "candidates": self._list(c, "candidates", owner["tenant_id"], owner["task_id"]),
                            "budget": {**self._budget(c, owner["tenant_id"], owner["task_id"]),
                                       "limit": task["contract"]["budget_units"]}}
            else:
                snapshot = self._snapshot(c, guard, owner["tenant_id"], owner["task_id"])
            if context is not None and not skills:
                from .recovery import validate_checkpoint_dispatches
                validate_checkpoint_dispatches(context, payload, snapshot["dispatches"], owner)
            checkpoint_id = digest_json([owner, manifest, snapshot["frontier"]])
            checkpoint = {
                "checkpoint_id": checkpoint_id,
                "owner": owner,
                "manifest": freeze(manifest),
                "contract": task["contract"],
                "graph": snapshot["nodes"],
                "accepted_frontier": snapshot["candidates"],
                "dispatch_frontier": [d["dispatch_id"] for d in snapshot["dispatches"]],
                "pending_dispatches": [
                    d
                    for d in snapshot["dispatches"]
                    if d["attempt_id"] == owner["attempt_id"]
                    and d["effect_state"] in ("in_flight", "unknown")
                ],
                "budget": snapshot["budget"],
                "frontier": snapshot["frontier"],
                "created_at": self._now(c),
            }
            checkpoint.update(tenant_id=owner["tenant_id"], task_id=owner["task_id"])
            self._owner(c, guard, owner)
            self._save(
                c, "checkpoints", checkpoint_id, owner["tenant_id"], owner["task_id"], checkpoint, new=True
            )
            self._event(
                c,
                guard,
                owner["tenant_id"],
                owner["task_id"],
                "checkpoint.accepted",
                {"checkpoint_id": checkpoint_id},
            )
            return checkpoint

    def _snapshot(self, c, guard, tenant_id, task_id):
        task = self._task(c, tenant_id, task_id)
        result = {
            "task": task,
            "budget": {**self._budget(c, tenant_id, task_id), "limit": task["contract"]["budget_units"]},
            "frontier": {
                "service_incarnation": guard["service_incarnation"],
                "sequence": task["event_sequence"],
            },
            "recovery_frontier": guard["recovery_frontier"],
            "quarantined": guard["quarantined"],
        }
        for name in (
            "nodes",
            "attempts",
            "dispatches",
            "sandboxes",
            "candidates",
            "checkpoints",
            "verifications",
            "reviews",
        ):
            result[name] = self._list(c, name, tenant_id, task_id)
        return result

    def snapshot(self, tenant_id, task_id):
        with self._read() as c:
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            return self._snapshot(c, guard, tenant_id, task_id)

    def _cursor(self, guard, tenant_id, task_id, sequence):
        payload = canonical_bytes(
            {
                "incarnation": guard["service_incarnation"],
                "tenant_id": tenant_id,
                "task_id": task_id,
                "sequence": sequence,
            }
        )
        signature = hmac.new(guard["cursor_secret"].encode(), payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")

    def events(self, tenant_id, task_id, cursor=None, limit=100):
        strict_int(limit, "event limit", 1, 1000)
        with self._read() as c:
            task = self._task(c, tenant_id, task_id)
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            sequence = 0
            if cursor:
                try:
                    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                    payload, signature = raw[:-32], raw[-32:]
                    expected = hmac.new(guard["cursor_secret"].encode(), payload, hashlib.sha256).digest()
                    if not hmac.compare_digest(signature, expected):
                        raise ValueError("invalid signature")
                    decoded = json.loads(payload)
                    if decoded["tenant_id"] != tenant_id or decoded["task_id"] != task_id:
                        raise NotFound("cursor is outside task authority")
                    if decoded["incarnation"] != guard["service_incarnation"]:
                        raise ResetRequired(
                            "service incarnation changed; reset from snapshot",
                            self._snapshot(c, guard, tenant_id, task_id),
                        )
                    sequence = strict_int(decoded["sequence"], "cursor sequence")
                except (ValueError, KeyError, TypeError) as exc:
                    raise Conflict("invalid event cursor") from exc
                if sequence < task["retained_from"] - 1:
                    raise ResetRequired(
                        "event retention gap; reset from snapshot",
                        self._snapshot(c, guard, tenant_id, task_id),
                    )
                if sequence > task["event_sequence"]:
                    raise ResetRequired(
                        "cursor exceeds restored event frontier", self._snapshot(c, guard, tenant_id, task_id)
                    )
            values = (
                c.execute(
                    sa.select(event_rows.c.data)
                    .where(
                        event_rows.c.tenant_id == tenant_id,
                        event_rows.c.task_id == task_id,
                        event_rows.c.sequence > sequence,
                    )
                    .order_by(event_rows.c.sequence)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            events = [freeze(value) for value in values]
            for event in events:
                event["cursor"] = self._cursor(guard, tenant_id, task_id, event["sequence"])
            end = events[-1]["sequence"] if events else sequence
            return {
                "events": events,
                "cursor": self._cursor(guard, tenant_id, task_id, end),
                "frontier": task["event_sequence"],
                "service_incarnation": guard["service_incarnation"],
            }

    def integrate(self, tenant_id, task_id, generation, candidate_ids, expected_revision, manifest):
        strict_int(generation, "generation", 1)
        strict_int(expected_revision, "expected_revision")
        if (
            not isinstance(candidate_ids, list)
            or not candidate_ids
            or len(set(candidate_ids)) != len(candidate_ids)
        ):
            raise ValueError("integration needs unique ordered parents")
        manifest = self._prepare_manifest(tenant_id, task_id, manifest)
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            self._eligible(c, guard, task, generation)
            if task["head_revision"] != expected_revision:
                raise Conflict("head compare-and-swap failed")
            parents = [
                self._get(c, "candidates", candidate_id, tenant_id, task_id) for candidate_id in candidate_ids
            ]
            if any(parent["generation"] != generation for parent in parents):
                raise Fenced("integration parent generation stale")
            nodes = self._list(c, "nodes", tenant_id, task_id)
            accepted = {node["candidate_id"] for node in nodes if node["status"] == "completed"}
            if any(p["kind"] != "worker" or p["candidate_id"] not in accepted for p in parents):
                raise Fenced("integration parent is not an accepted worker output")
            # Stable graph order is recorded; callers reconstruct this exact order externally.
            order = {n["node_id"]: i for i, n in enumerate(nodes)}
            canonical_parents = sorted(parents, key=lambda p: order[p["owner"]["node_id"]])
            if [p["candidate_id"] for p in canonical_parents] != candidate_ids:
                raise Conflict("parents must use deterministic node order")
            manifest = self._manifest(task, manifest)
            candidate_id = digest_json([task_id, generation, expected_revision + 1, candidate_ids, manifest])
            candidate = {
                "candidate_id": candidate_id,
                "tenant_id": tenant_id,
                "task_id": task_id,
                "generation": generation,
                "kind": "integration",
                "parent_candidate_ids": candidate_ids,
                "manifest": manifest,
                "tree_digest": manifest["tree_digest"],
                "contract_digest": task["contract_digest"],
                "revision": expected_revision + 1,
                "accepted_at": self._now(c),
            }
            self._eligible(c, guard, task, generation)
            self._save(c, "candidates", candidate_id, tenant_id, task_id, candidate, new=True)
            task.update(head_revision=expected_revision + 1, head_candidate_id=candidate_id)
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(
                c,
                guard,
                tenant_id,
                task_id,
                "head.integrated",
                {"candidate_id": candidate_id, "revision": task["head_revision"], "parents": candidate_ids},
            )
            self._command(c, guard, task, "verify", {"candidate_id": candidate_id})
            return candidate

    def record_verification(
        self,
        tenant_id,
        task_id,
        generation,
        candidate_id,
        tree_digest,
        grader_digest,
        environment_digest,
        outcome,
        evidence_ref,
    ):
        strict_int(generation, "generation", 1)
        if outcome not in ("pass", "fail", "error"):
            raise ValueError("verification outcome must be pass/fail/error")
        evidence = self._evidence(tenant_id, task_id, evidence_ref)
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            self._eligible(c, guard, task, generation)
            candidate = self._get(c, "candidates", candidate_id, tenant_id, task_id)
            if candidate["generation"] != generation or task["head_candidate_id"] != candidate_id:
                raise Fenced("verification is not for current integrated head")
            if (
                tree_digest != candidate["tree_digest"]
                or grader_digest != task["contract"]["grader_digest"]
                or environment_digest != task["contract"]["environment_digest"]
            ):
                raise Conflict("verification tree/grader/environment mismatch")
            value = {
                "tenant_id": tenant_id,
                "task_id": task_id,
                "generation": generation,
                "candidate_id": candidate_id,
                "tree_digest": tree_digest,
                "grader_digest": grader_digest,
                "environment_digest": environment_digest,
                "contract_digest": task["contract_digest"],
                "outcome": outcome,
                "evidence_ref": evidence,
                "authority": "trusted-control-plane",
            }
            verification_id = digest_json(value)
            try:
                return self._get(c, "verifications", verification_id, tenant_id, task_id)
            except NotFound:
                pass
            value.update(verification_id=verification_id, recorded_at=self._now(c))
            self._eligible(c, guard, task, generation)
            self._save(c, "verifications", verification_id, tenant_id, task_id, value, new=True)
            self._event(c, guard, tenant_id, task_id, "verification.recorded", value)
            return value

    def publish_review(
        self, tenant_id, task_id, generation, candidate_id, verification_id, expected_revision
    ):
        strict_int(generation, "generation", 1)
        strict_int(expected_revision, "expected_revision")
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            existing = self._list(c, "reviews", tenant_id, task_id)
            if task["execution_state"] == "review_eligible" and existing:
                old = existing[-1]
                if (old["generation"], old["candidate_id"], old["verification_id"], old["revision"]) == (
                    generation,
                    candidate_id,
                    verification_id,
                    expected_revision,
                ):
                    return old
            self._eligible(c, guard, task, generation)
            if task["head_revision"] != expected_revision or task["head_candidate_id"] != candidate_id:
                raise Conflict("review head compare-and-swap failed")
            candidate = self._get(c, "candidates", candidate_id, tenant_id, task_id)
            nodes = self._list(c, "nodes", tenant_id, task_id)
            if (
                not nodes
                or any(n["status"] != "completed" for n in nodes)
                or set(candidate.get("parent_candidate_ids", [])) != {n["candidate_id"] for n in nodes}
            ):
                raise Fenced("review requires the complete accepted graph frontier")
            verification = self._get(c, "verifications", verification_id, tenant_id, task_id)
            if (
                verification["outcome"] != "pass"
                or verification["candidate_id"] != candidate_id
                or verification["generation"] != generation
                or verification["tree_digest"] != candidate["tree_digest"]
                or verification["contract_digest"] != task["contract_digest"]
            ):
                raise Fenced("no current exact passing verifier receipt")
            decision_time = self._eligible(
                c, guard, task, generation
            )  # final DB-time fenced eligibility decision
            review_id = _id()
            review = {
                "review_id": review_id,
                "tenant_id": tenant_id,
                "task_id": task_id,
                "generation": generation,
                "candidate_id": candidate_id,
                "verification_id": verification_id,
                "revision": expected_revision,
                "tree_digest": candidate["tree_digest"],
                "decision_time": decision_time,
                "review_deadline": task["contract"]["review_deadline"],
                "status": "pending",
            }
            self._save(c, "reviews", review_id, tenant_id, task_id, review, new=True)
            task.update(
                execution_state="review_eligible",
                review_state="pending",
                review_id=review_id,
                authority_revoked_at=review["decision_time"],
            )
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(c, guard, tenant_id, task_id, "review.published", review)
            self._command(c, guard, task, "review_ready", {"review_id": review_id})
            return review

    def record_review(self, tenant_id, task_id, review_id, reviewer, decision, key):
        identity(reviewer, "reviewer")
        identity(key, "review key")
        if decision not in ("accepted", "rejected", "accept", "reject"):
            raise ValueError("decision must be accepted/rejected")
        decision = {"accept": "accepted", "reject": "rejected"}.get(decision, decision)
        parameters = {"review_id": review_id, "reviewer": reviewer, "decision": decision, "key": key}
        receipt_id = digest_json([tenant_id, key])
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            try:
                old = self._get(c, "review_decisions", receipt_id, tenant_id)
            except NotFound:
                old = None
            if old:
                if old["parameters"] != parameters or old["task_id"] != task_id:
                    raise Conflict("review key binds changed decision")
                return old
            review = self._get(c, "reviews", review_id, tenant_id, task_id)
            if (
                task["execution_state"] != "review_eligible"
                or task.get("review_id") != review_id
                or review["status"] != "pending"
            ):
                raise Fenced("review no longer current")
            if self._now(c) > review["review_deadline"]:
                raise Fenced("database review deadline elapsed")
            value = {
                "decision_id": receipt_id,
                "parameters": parameters,
                "task_id": task_id,
                "decision": decision,
                "reviewer": reviewer,
                "recorded_at": self._now(c),
            }
            self._save(c, "review_decisions", receipt_id, tenant_id, task_id, value, new=True)
            review["status"] = decision
            review["decision_id"] = receipt_id
            self._save(c, "reviews", review_id, tenant_id, task_id, review)
            task["review_state"] = decision
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(c, guard, tenant_id, task_id, "review.decided", value)
            return value

    def list_outbox(self, limit=100, kinds=None):
        strict_int(limit, "outbox limit", 1, 1000)
        if kinds is not None:
            if not isinstance(kinds, (list, tuple, set, frozenset)):
                raise ValueError("outbox kinds must be a collection")
            kinds = {identity(kind, "outbox kind") for kind in kinds}
        with self.engine.connect() as c:
            pending = (
                value
                for value in self._list(c, "outbox")
                if not value["acked"] and (kinds is None or value["kind"] in kinds)
            )
            return sorted(pending, key=lambda v: (v["created_at"], v["task_sequence"], v["command_id"]))[
                :limit
            ]

    def ack_outbox(self, command_id):
        with self._tx() as (c, guard):
            value = self._get(c, "outbox", command_id)
            if not value["acked"]:
                value.update(acked=True, acknowledged_at=self._now(c))
                self._save(c, "outbox", command_id, value["tenant_id"], value["task_id"], value)
                self._event(
                    c, guard, value["tenant_id"], value["task_id"], "outbox.acked", {"command_id": command_id}
                )

    def set_admission(self, accept_new_tasks: bool):
        """Trusted drain switch; existing ownership retains execution permission."""
        if type(accept_new_tasks) is not bool:
            raise ValueError("accept_new_tasks must be bool")
        with self._tx() as (c, guard):
            if guard["quarantined"] and accept_new_tasks:
                raise Fenced("restore reconciliation required")
            guard["accept_new_tasks"] = accept_new_tasks
            c.execute(authority.update().where(authority.c.id == 1).values(data=guard))
            return {k: v for k, v in guard.items() if k != "cursor_secret"}

    def quarantine_restore(self, new_incarnation, recovery_frontier):
        identity(new_incarnation, "new incarnation")
        if not isinstance(recovery_frontier, dict) or not recovery_frontier:
            raise ValueError("restore requires explicit recovery frontier")
        with self._tx() as (c, guard):
            if new_incarnation == guard["service_incarnation"]:
                raise Conflict("restore must issue a fresh incarnation")
            guard.update(
                service_incarnation=new_incarnation,
                accept_new_tasks=False,
                execution_enabled=False,
                quarantined=True,
                recovery_frontier=freeze(recovery_frontier),
                reconciliation_evidence=None,
            )
            c.execute(authority.update().where(authority.c.id == 1).values(data=guard))
            for task in self._list(c, "tasks"):
                for attempt in self._list(c, "attempts", task["tenant_id"], task["task_id"]):
                    if attempt["status"] == "running":
                        attempt["status"] = "revoked"
                        self._save(
                            c, "attempts", attempt["attempt_id"], task["tenant_id"], task["task_id"], attempt
                        )
                self._event(
                    c,
                    guard,
                    task["tenant_id"],
                    task["task_id"],
                    "service.restore_quarantined",
                    {"recovery_frontier": recovery_frontier},
                )
                for sandbox in self._list(c, "sandboxes", task["tenant_id"], task["task_id"]):
                    if sandbox["status"] != "retired":
                        self._command(c, guard, task, "stop_sandbox", {"sandbox_id": sandbox["sandbox_id"]})

    def resume_after_reconciliation(self, evidence_ref):
        # Operator evidence explicitly describes prior actor retirement and the
        # beyond-backup interval. A bare reconciled=true can never authorize this.
        if not isinstance(evidence_ref, dict) or any(
            not isinstance(evidence_ref.get(field), dict) or not evidence_ref[field]
            for field in ("actor_fencing", "effect_reconciliation", "recovery_frontier")
        ):
            raise Fenced("operator evidence must bind actor fencing, effects and recovery frontier")
        with self._tx() as (c, guard):
            if not guard["quarantined"]:
                raise Conflict("service is not quarantined")
            if evidence_ref["recovery_frontier"] != guard["recovery_frontier"]:
                raise Conflict("reconciliation frontier mismatch")
            if any(s["status"] != "retired" for s in self._list(c, "sandboxes")):
                raise Fenced("pre-restore environments not retired")
            if any(
                d["effect_state"] in ("in_flight", "unknown") or d["billing_state"] != "settled"
                for d in self._list(c, "dispatches")
            ):
                raise Fenced("unreconciled effects or billing exposure remain")
            guard.update(
                accept_new_tasks=True,
                execution_enabled=True,
                quarantined=False,
                reconciliation_evidence=freeze(evidence_ref),
            )
            c.execute(authority.update().where(authority.c.id == 1).values(data=guard))
            for task in self._list(c, "tasks"):
                self._event(
                    c,
                    guard,
                    task["tenant_id"],
                    task["task_id"],
                    "service.reconciled",
                    {"evidence_ref": evidence_ref},
                )

    def authorize_artifact(self, tenant_id, task_id, artifact_digest):
        digest(artifact_digest)
        snapshot = self.snapshot(tenant_id, task_id)
        found = None

        def walk(value):
            nonlocal found
            if isinstance(value, dict):
                if (
                    {"digest", "size", "tenant_id", "task_id"} <= set(value)
                    and value["digest"] == artifact_digest
                    and value["tenant_id"] == tenant_id
                    and value["task_id"] == task_id
                ):
                    found = freeze(value)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(snapshot)
        if found is None:
            raise NotFound("artifact is not bound to accepted task evidence")
        return found

    def service_state(self):
        with self.engine.connect() as c:
            guard = freeze(c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one())
            guard.pop("cursor_secret", None)
            return guard

    def reserve_environment(self, tenant_id, task_id, generation, kind, reservation_id):
        """Trusted auxiliary environment admission, distinct from patch allowance."""
        strict_int(generation, "generation", 1)
        identity(reservation_id, "reservation_id")
        if kind not in ("verifier", "integrator"):
            raise Unsupported("unsupported auxiliary environment role")
        sandbox_id = digest_json([tenant_id, task_id, "auxiliary", reservation_id])
        parameters = {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "generation": generation,
            "kind": kind,
            "reservation_id": reservation_id,
        }
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            self._eligible(c, guard, task, generation)
            try:
                old = self._get(c, "sandboxes", sandbox_id, tenant_id, task_id)
            except NotFound:
                old = None
            if old:
                if old["parameters"] != parameters:
                    raise Conflict("auxiliary reservation ID binds changed parameters")
                return {**old, "duplicate": True}
            occupied = [s for s in self._list(c, "sandboxes") if s["status"] != "retired"]
            if (
                len(occupied) >= guard["service_slot_limit"]
                or sum(s["tenant_id"] == tenant_id for s in occupied) >= guard["tenant_slot_limit"]
            ):
                raise CapacityExceeded("aggregate physical environment capacity exhausted")
            if any(s["task_id"] == task_id and s.get("kind", "patch") == kind for s in occupied):
                raise CapacityExceeded("one auxiliary environment per role per task")
            sandbox = {
                **parameters,
                "parameters": parameters,
                "sandbox_id": sandbox_id,
                "attempt_id": None,
                "service_incarnation": guard["service_incarnation"],
                "status": "reserved",
                "retirement_evidence": None,
            }
            self._eligible(c, guard, task, generation)
            self._save(c, "sandboxes", sandbox_id, tenant_id, task_id, sandbox, new=True)
            self._event(c, guard, tenant_id, task_id, "environment.reserved", sandbox)
            return {**sandbox, "duplicate": False}

    def fail_execution(self, tenant_id, task_id, generation, reason, evidence_ref):
        """Trusted terminal failure; cleanup/billing remain separate obligations."""
        strict_int(generation, "generation", 1)
        if reason not in (
            "candidate_failed",
            "budget_exhausted",
            "deadline_exceeded",
            "infrastructure_failed",
            "effect_unknown",
        ):
            raise ValueError("unsupported terminal failure reason")
        evidence = self._evidence(tenant_id, task_id, evidence_ref)
        with self._tx() as (c, guard):
            task = self._task(c, tenant_id, task_id)
            if task["execution_state"] == "failed":
                if task.get("failure") == {
                    "generation": generation,
                    "reason": reason,
                    "evidence_ref": evidence,
                }:
                    return task
                raise Conflict("terminal failure already binds different evidence")
            decision_time = self._eligible(
                c, guard, task, generation, allow_expired=reason == "deadline_exceeded"
            )
            if reason == "deadline_exceeded" and decision_time <= task["contract"]["execution_deadline"]:
                raise Conflict("deadline has not elapsed according to database time")
            task["generation"] += 1
            task.update(
                execution_state="failed",
                authority_revoked_at=decision_time,
                failure={"generation": generation, "reason": reason, "evidence_ref": evidence},
            )
            for attempt in self._list(c, "attempts", tenant_id, task_id):
                if attempt["status"] == "running":
                    attempt["status"] = "revoked"
                    self._save(c, "attempts", attempt["attempt_id"], tenant_id, task_id, attempt)
            for sandbox in self._list(c, "sandboxes", tenant_id, task_id):
                if sandbox["status"] != "retired":
                    sandbox["status"] = "retirement_requested"
                    self._save(c, "sandboxes", sandbox["sandbox_id"], tenant_id, task_id, sandbox)
                    self._command(
                        c,
                        guard,
                        task,
                        "stop_sandbox",
                        {"sandbox_id": sandbox["sandbox_id"], "target_generation": generation},
                    )
            self._save(c, "tasks", task_id, tenant_id, task_id, task)
            self._event(c, guard, tenant_id, task_id, "task.failed", task["failure"])
            return self._task(c, tenant_id, task_id)

    def capture_failure_source(
        self, tenant_id, task_id, *, max_rows=10_000, max_events=10_000,
        max_source_bytes=16_777_216, page_size=500,
    ):
        """Read one bounded, deterministic failure source without granting authority."""
        identity(tenant_id, "tenant_id")
        identity(task_id, "task_id")
        limits = dict(max_rows=max_rows, max_events=max_events,
                      max_source_bytes=max_source_bytes, page_size=page_size)
        for name, lower, upper in (("max_rows", 1, 10_000), ("max_events", 1, 10_000),
                                   ("max_source_bytes", 1024, 16_777_216), ("page_size", 1, 1000)):
            strict_int(limits[name], name, lower, upper)
        names = ("tasks", "nodes", "attempts", "dispatches", "sandboxes", "candidates",
                 "checkpoints", "verifications", "reviews", "receipts", "submissions")
        logical = {"tasks": "task_id", "nodes": "node_id", "attempts": "attempt_id",
                   "dispatches": "dispatch_id", "sandboxes": "sandbox_id",
                   "candidates": "candidate_id", "checkpoints": "checkpoint_id",
                   "verifications": "verification_id", "reviews": "review_id",
                   "receipts": "receipt_id", "submissions": "key"}

        def fail_limit():
            raise ValueError("capture_limit_exceeded: bounded source")

        def check_scope(value):
            if isinstance(value, dict):
                for key, expected in (("tenant_id", tenant_id), ("task_id", task_id)):
                    if key in value and value[key] != expected:
                        raise ValueError("invalid_source:invalid_scope")
                for key, child in value.items():
                    if key not in ("files", "base_files"):
                        check_scope(child)
            elif isinstance(value, list):
                for child in value:
                    check_scope(child)

        with self._read() as c:
            if c.execute(sa.select(schema_versions.c.version)).scalars().all() != [SCHEMA_VERSION]:
                raise Unsupported("unsupported capture schema")

            def encoded_size(column):
                return (sa.func.length(sa.cast(column, sa.LargeBinary))
                        if c.dialect.name == "sqlite"
                        else sa.func.octet_length(sa.cast(column, sa.Text)))

            guard_size = c.execute(sa.select(encoded_size(authority.c.data))
                                   .where(authority.c.id == 1)).scalar_one()
            task_table = TABLES["tasks"]
            task_filter = sa.and_(task_table.c.id == task_id, task_table.c.tenant_id == tenant_id,
                                  task_table.c.task_id == task_id)
            task_size = c.execute(sa.select(encoded_size(task_table.c.data))
                                  .where(task_filter)).scalar_one_or_none()
            if task_size is None:
                raise NotFound("tasks record not found")
            if guard_size + task_size > max_source_bytes:
                fail_limit()
            guard = c.execute(sa.select(authority.c.data).where(authority.c.id == 1)).scalar_one()
            try:
                task = self._task(c, tenant_id, task_id)
                if not isinstance(task, dict):
                    raise ValueError("invalid task")
                strict_int(task["generation"], "generation", 1)
                check_scope(task)
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("invalid_source:invalid_identity") from exc
            try:
                frontier = strict_int(task["event_sequence"], "frontier", 1)
                retained = strict_int(task["retained_from"], "retained_from", 1)
                identity(guard["service_incarnation"], "service_incarnation")
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("invalid_source:invalid_identity") from exc
            counts = {}
            total_rows, total_bytes = 0, guard_size
            for name in names:
                table = TABLES[name]
                count, size = c.execute(sa.select(sa.func.count(),
                    sa.func.coalesce(sa.func.sum(encoded_size(table.c.data)), 0)).where(
                    table.c.tenant_id == tenant_id, table.c.task_id == task_id)).one()
                counts[name] = count
                total_rows += count
                total_bytes += size
                if total_rows > max_rows or total_bytes > max_source_bytes:
                    fail_limit()
            event_filter = sa.and_(event_rows.c.tenant_id == tenant_id,
                                  event_rows.c.task_id == task_id, event_rows.c.sequence <= frontier)
            count, size = c.execute(sa.select(sa.func.count(),
                sa.func.coalesce(sa.func.sum(encoded_size(event_rows.c.data)), 0))
                .where(event_filter)).one()
            if count > max_events or total_bytes + size > max_source_bytes:
                fail_limit()
            try:
                snapshot = self._snapshot(c, guard, tenant_id, task_id)
                receipts = self._list(c, "receipts", tenant_id, task_id)
                submissions = self._list(c, "submissions", tenant_id, task_id)
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("invalid_source:invalid_identity") from exc
            for name in names[1:]:
                rows = receipts if name == "receipts" else submissions if name == "submissions" else snapshot[name]
                for row in rows:
                    if not isinstance(row, dict) or logical[name] not in row:
                        raise ValueError("invalid_source:invalid_identity")
                    try:
                        identity(row[logical[name]], "row identity")
                        if "generation" in row:
                            strict_int(row["generation"], "generation", 1)
                        if name == "attempts":
                            strict_int(row["allowance_remaining"], "allowance_remaining")
                            validate_owner(row["owner"])
                        if name == "dispatches":
                            strict_int(row["bound_units"], "bound_units")
                            if row["actual_units"] is not None:
                                strict_int(row["actual_units"], "actual_units")
                            validate_owner(row["owner"])
                        check_scope(row)
                    except (KeyError, ValueError, TypeError, Fenced) as exc:
                        raise ValueError("invalid_source:invalid_identity") from exc
                rows.sort(key=lambda row: (row[logical[name]], canonical_bytes(row)))
                if len({row[logical[name]] for row in rows}) != len(rows):
                    raise ValueError("invalid_source:duplicate_identity")
            events, after = [], 0
            while True:
                page = c.execute(sa.select(event_rows.c.event_id, event_rows.c.sequence, event_rows.c.data)
                    .where(event_filter, event_rows.c.sequence > after)
                    .order_by(event_rows.c.sequence).limit(page_size)).all()
                if not page:
                    break
                for event_id, sequence, event in page:
                    if not isinstance(event, dict) or event.get("event_id") != event_id or event.get("sequence") != sequence:
                        raise ValueError("invalid_source:invalid_event")
                    check_scope(event)
                    events.append(freeze(event))
                after = page[-1][1]
            reasons = []
            if retained != 1:
                reasons.append("retention_gap")
            if len(events) != frontier or any(e["sequence"] != i for i, e in enumerate(events, 1)):
                reasons.append("event_sequence_gap")
            if any(e.get("service_incarnation") != guard["service_incarnation"] for e in events):
                reasons.append("mixed_incarnation")
            body = dict(snapshot=snapshot, receipts=receipts, submissions=submissions, events=events)
            source = dict(schema=1, evidence_kind="runtime_failure_source", tenant_id=tenant_id,
                          task_id=task_id, **body, capture=dict(
                method="runtime_store_repeatable_read_v1", schema_version=SCHEMA_VERSION,
                service_incarnation=guard["service_incarnation"], frontier=frontier,
                retained_from=retained, history_start=1, history_end=frontier,
                status="incomplete" if reasons else "complete", reasons=sorted(set(reasons)),
                limits=limits, table_counts=counts, event_count=len(events),
                source_bytes=len(canonical_bytes(body))))
            if len(canonical_bytes(source)) > max_source_bytes:
                fail_limit()
            return freeze(source)
