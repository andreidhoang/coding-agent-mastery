"""Durable local Docker instance intent; physical cleanup never grants task authority."""
from __future__ import annotations

from copy import deepcopy
import math
import os
import re

from .artifacts import canonical_bytes, digest_json, digest_bytes
from .contracts import Conflict, digest, strict_int

PROFILE = "docker_environment_journal_v1"
OBS_PROFILE = "docker_environment_observation_v1"
JOURNAL_CAP, OBS_CAP = 65536, 16384
JOURNAL_KEYS = set("schema profile revision phase backend source max_instances instances".split())
INSTANCE_KEYS = set("ordinal intent_id name creation_nonce launch state container_id create_observation_ref retirement_observation_ref".split())
SOURCE_KEYS = set("generation service_incarnation purpose tree_digest input_digest grader_digest environment_digest".split())
LAUNCH_KEYS = set("image memory_mb cpus pids disk_mb timeout_seconds policy_digest".split())
OBS_KEYS = set("schema profile operation_id kind backend intent_id ordinal name creation_nonce launch_digest container_id status diagnostic".split())
POLICY = {"schema": 1, "pull": "never", "network": "none", "read_only": True,
          "user": "65534:65534", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges"],
          "host_mounts": [], "memory_swap_equals_memory": True, "ulimits": {"nofile": 128, "fsize": 8388608},
          "log_driver": "none", "workspace": "rw,nosuid,nodev,size={disk_mb}m,mode=1777",
          "tmp": "rw,noexec,nosuid,nodev,size=8m,mode=1777", "workdir": "/workspace",
          "entrypoint": ["python"], "command": ["-I", "-c", "import time; time.sleep(3600)"]}


def closed(value, keys, label):
    if type(value) is not dict or set(value) != keys:
        raise ValueError("invalid closed " + label)


def ascii_label(value, label):
    if type(value) is not str or not value or len(value.encode("utf-8")) > 128 or not value.isascii() or any(ord(x) < 33 or ord(x) > 126 for x in value):
        raise ValueError("invalid " + label)
    return value


def validate_backend(value):
    closed(value, {"kind", "backend_id", "daemon_id"}, "environment backend")
    if value["kind"] != "docker_local":
        raise ValueError("unsupported environment backend")
    ascii_label(value["backend_id"], "backend identity")
    ascii_label(value["daemon_id"], "daemon identity")
    return deepcopy(value)


def validate_source(value):
    closed(value, SOURCE_KEYS, "environment source")
    strict_int(value["generation"], "environment generation", 1)
    ascii_label(value["service_incarnation"], "service incarnation")
    if value["purpose"] not in {"fixture", "worker", "final"}:
        raise ValueError("unsupported environment purpose")
    for key in SOURCE_KEYS - {"generation", "service_incarnation", "purpose"}:
        digest(value[key], key)
    return deepcopy(value)


def launch_value(image, *, memory_mb=192, cpus=0.5, pids=32, disk_mb=16, timeout=20):
    value = {"image": image, "memory_mb": memory_mb, "cpus": cpus, "pids": pids,
             "disk_mb": disk_mb, "timeout_seconds": timeout, "policy_digest": digest_json(POLICY)}
    return validate_launch(value)


def validate_launch(value):
    closed(value, LAUNCH_KEYS, "environment launch")
    if type(value["image"]) is not str or not re.fullmatch(r"(?:sha256:[0-9a-f]{64}|[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64})", value["image"]):
        raise ValueError("immutable Docker image required")
    for key, lower, upper in (("memory_mb", 32, 4096), ("pids", 4, 256), ("disk_mb", 1, 128)):
        strict_int(value[key], key, lower, upper)
    for key, lower, upper in (("cpus", 0, 4), ("timeout_seconds", 0, 3600)):
        number = value[key]
        if type(number) not in {int, float} or not math.isfinite(number) or not lower < number <= upper:
            raise ValueError("environment limit outside reference envelope")
    if value["policy_digest"] != digest_json(POLICY):
        raise ValueError("environment policy mismatch")
    return deepcopy(value)


def intent_identity(sandbox_id, ordinal, source, backend, launch):
    return digest_json({"sandbox_id": sandbox_id, "ordinal": ordinal, "source": source,
                        "backend": backend, "launch": launch})


def validate_ref(ref, tenant=None, task=None):
    closed(ref, {"tenant_id", "task_id", "digest", "size", "content_type"}, "environment observation reference")
    digest(ref["digest"])
    strict_int(ref["size"], "observation size", 0, OBS_CAP)
    if ref["content_type"] != "application/json" or tenant is not None and (ref["tenant_id"] != tenant or ref["task_id"] != task):
        raise ValueError("environment observation outside scope")


def validate_journal(value, sandbox_id=None, tenant=None, task=None):
    closed(value, JOURNAL_KEYS, "environment journal")
    if type(value["schema"]) is not int or value["schema"] != 1 or value["profile"] != PROFILE:
        raise ValueError("unsupported environment journal schema")
    strict_int(value["revision"], "journal revision", 1)
    strict_int(value["max_instances"], "instance bound", 1, 32)
    if value["phase"] not in {"open", "cleanup_requested", "retired"}:
        raise ValueError("invalid environment phase")
    validate_backend(value["backend"])
    validate_source(value["source"])
    if type(value["instances"]) is not list or len(value["instances"]) > value["max_instances"]:
        raise ValueError("environment instance bound exceeded")
    unresolved = 0
    for ordinal, instance in enumerate(value["instances"]):
        closed(instance, INSTANCE_KEYS, "environment instance")
        strict_int(instance["ordinal"], "instance ordinal", 0, 31)
        if instance["ordinal"] != ordinal or instance["state"] not in {"create_intent", "bound", "create_rejected", "retired"}:
            raise ValueError("invalid environment instance order or state")
        digest(instance["intent_id"])
        if (instance["name"] != "cam-sandbox-" + instance["intent_id"][:48]
                or type(instance["creation_nonce"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", instance["creation_nonce"])):
            raise ValueError("environment nonce or name mismatch")
        validate_launch(instance["launch"])
        if sandbox_id is not None and instance["intent_id"] != intent_identity(sandbox_id, ordinal, value["source"], value["backend"], instance["launch"]):
            raise ValueError("environment intent mismatch")
        cid = instance["container_id"]
        if cid is not None and (type(cid) is not str or not re.fullmatch(r"[0-9a-f]{64}", cid)):
            raise ValueError("invalid immutable container ID")
        if instance["state"] in {"bound", "retired"} and cid is None or instance["state"] in {"create_intent", "create_rejected"} and cid is not None:
            raise ValueError("environment state/container identity mismatch")
        for key in ("create_observation_ref", "retirement_observation_ref"):
            if instance[key] is not None:
                validate_ref(instance[key], tenant, task)
        if (instance["state"] in {"bound", "create_rejected", "retired"} and instance["create_observation_ref"] is None
                or instance["state"] == "retired" and instance["retirement_observation_ref"] is None):
            raise ValueError("terminal environment lacks original observation")
        unresolved += instance["state"] in {"create_intent", "bound"}
        if ordinal < len(value["instances"]) - 1 and instance["state"] not in {"retired", "create_rejected"}:
            raise ValueError("prior environment instance unresolved")
    if unresolved > 1 or value["phase"] == "retired" and unresolved:
        raise ValueError("unresolved physical environment")
    if len(canonical_bytes(value)) > JOURNAL_CAP:
        raise ValueError("environment journal byte bound exceeded")
    return deepcopy(value)


def observation_value(journal, instance, kind, status, container_id=None, diagnostic=""):
    value = {"schema": 1, "profile": OBS_PROFILE, "kind": kind, "backend": journal["backend"],
             "intent_id": instance["intent_id"], "ordinal": instance["ordinal"], "name": instance["name"],
             "creation_nonce": instance["creation_nonce"], "launch_digest": digest_json(instance["launch"]),
             "container_id": container_id, "status": status, "diagnostic": diagnostic}
    value["operation_id"] = digest_json(value)
    return value


def validate_observation(value):
    closed(value, OBS_KEYS, "environment observation")
    if type(value["schema"]) is not int or value["schema"] != 1 or value["profile"] != OBS_PROFILE:
        raise ValueError("unsupported environment observation")
    if value["kind"] not in {"create", "retirement"} or value["status"] not in {"bound", "create_rejected", "absent", "unresolved"}:
        raise ValueError("invalid environment observation kind/status")
    if (value["kind"] == "create" and value["status"] == "absent"
            or value["kind"] == "retirement" and value["status"] in {"bound", "create_rejected"}):
        raise ValueError("invalid environment observation transition")
    validate_backend(value["backend"])
    strict_int(value["ordinal"], "observation ordinal", 0, 31)
    digest(value["intent_id"])
    digest(value["launch_digest"])
    if value["name"] != "cam-sandbox-" + value["intent_id"][:48] or type(value["creation_nonce"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", value["creation_nonce"]):
        raise ValueError("invalid environment observation identity")
    cid = value["container_id"]
    if cid is not None and (type(cid) is not str or not re.fullmatch(r"[0-9a-f]{64}", cid)):
        raise ValueError("invalid environment observation container")
    if value["status"] in {"bound", "absent"} and cid is None or value["status"] == "create_rejected" and cid is not None:
        raise ValueError("invalid environment observation proof")
    if type(value["diagnostic"]) is not str or len(value["diagnostic"].encode()) > 1024:
        raise ValueError("environment diagnostic bound exceeded")
    if value["operation_id"] != digest_json({k: v for k, v in value.items() if k != "operation_id"}):
        raise ValueError("environment observation operation mismatch")
    if len(canonical_bytes(value)) > OBS_CAP:
        raise ValueError("environment observation byte bound exceeded")
    return deepcopy(value)


def read_observation(artifacts, tenant, task, ref):
    validate_ref(ref, tenant, task)
    raw = artifacts.get(tenant, task, ref["digest"], max_bytes=OBS_CAP)
    if len(raw) != ref["size"] or digest_bytes(raw) != ref["digest"]:
        raise ValueError("environment observation integrity mismatch")
    from .protocol import strict_json
    value = strict_json(raw.decode("utf-8"), OBS_CAP)
    validate_observation(value)
    if canonical_bytes(value) != raw:
        raise ValueError("noncanonical environment observation")
    return value


def validate_terminal_observations(artifacts, tenant, task, journal):
    for instance in journal["instances"]:
        if instance["state"] not in {"retired", "create_rejected"}:
            continue
        pairs = [("create_observation_ref", "create", "create_rejected" if instance["state"] == "create_rejected" else "bound")]
        if instance["state"] == "retired":
            pairs.append(("retirement_observation_ref", "retirement", "absent"))
        for key, kind, status in pairs:
            value = read_observation(artifacts, tenant, task, instance[key])
            expected = observation_value(journal, instance, kind, status, instance["container_id"],
                "acknowledged_name_conflict" if status == "create_rejected" else "")
            if value != expected:
                raise ValueError("environment terminal evidence differs from recorded instance")


class DockerEnvironmentBackend:
    """Trusted local CLI transport. Nonce inventories and output/time are bounded."""
    def __init__(self, backend_id="local-docker", *, runner=None):
        from .execution import bounded_process
        self.backend_id = ascii_label(backend_id, "backend identity")
        self.runner = runner or bounded_process
        self.backend = self.identity()

    def identity(self):
        from .execution import _acknowledged_process_result
        server = self.runner(["docker", "info", "--format", "{{.ID}}"], timeout=20, max_output=256)
        context = self.runner(["docker", "context", "inspect", "--format", "{{json .}}"], timeout=20, max_output=4096)
        if not _acknowledged_process_result(server) or not _acknowledged_process_result(context):
            raise RuntimeError("Docker daemon identity unresolved")
        try:
            from .protocol import strict_json
            server_id = server["output"].decode().strip()
            details = strict_json(context["output"].decode("utf-8"), 4096)
            ascii_label(server_id, "Docker daemon identity")
            selected_context = os.environ.get("DOCKER_CONTEXT")
            configured_host = os.environ.get("DOCKER_HOST")
            if selected_context and selected_context != details["Name"]:
                raise ValueError("Docker selected context is ambiguous")
            effective = details["Endpoints"]["docker"]["Host"] if selected_context else (
                configured_host or details["Endpoints"]["docker"]["Host"])
            if type(effective) is not str or not re.fullmatch(r"unix:///[^\x00\r\n]+", effective):
                raise ValueError("local Unix Docker socket required")
            binding = {"server_id": server_id, "context": details["Name"],
                       "endpoint": details["Endpoints"]["docker"],
                       "configured_host": os.environ.get("DOCKER_HOST"),
                       "configured_context": os.environ.get("DOCKER_CONTEXT")}
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            raise RuntimeError("Docker daemon identity unresolved") from error
        return validate_backend({"kind": "docker_local", "backend_id": self.backend_id,
                                 "daemon_id": digest_json(binding)})

    def confirm(self, expected):
        if self.identity() != expected or expected != self.backend:
            raise RuntimeError("Docker daemon/backend identity changed")

    def inventory(self, *, nonce=None, container_id=None):
        from .execution import _acknowledged_process_result
        selector = "label=coding-agent-mastery-create-nonce=" + nonce if nonce else "id=" + container_id
        self.confirm(self.backend)
        result = self.runner(["docker", "ps", "-a", "--no-trunc", "--filter", selector,
                              "--format", "{{.ID}}"], timeout=30, max_output=132)
        ids = result["output"].decode(errors="replace").split()
        if not _acknowledged_process_result(result) or len(ids) > 1 or any(not re.fullmatch(r"[0-9a-f]{64}", cid) for cid in ids):
            raise RuntimeError("Docker inventory incomplete or ambiguous")
        if container_id is not None and ids and ids != [container_id]:
            raise RuntimeError("Docker inventory returned another immutable ID")
        return ids

    def inspect_owned(self, instance):
        from .execution import _acknowledged_process_result
        self.confirm(self.backend)
        cid = instance["container_id"]
        result = self.runner(["docker", "inspect", cid, "--format", "{{json .}}"], timeout=30, max_output=OBS_CAP)
        image = self.runner(["docker", "image", "inspect", instance["launch"]["image"], "--format", "{{.Id}}"], timeout=20, max_output=256)
        if not _acknowledged_process_result(result) or not _acknowledged_process_result(image):
            raise RuntimeError("Docker instance inspection unresolved")
        try:
            from .protocol import strict_json
            d = strict_json(result["output"].decode("utf-8"), OBS_CAP)
            config, host, launch = d["Config"], d["HostConfig"], instance["launch"]
            expected_tmpfs = {"/workspace": POLICY["workspace"].format(disk_mb=launch["disk_mb"]), "/tmp": POLICY["tmp"]}
            ulimits = {x["Name"]: (x["Soft"], x["Hard"]) for x in host["Ulimits"]}
            if any(type(host[key]) is not int for key in ("Memory", "MemorySwap", "NanoCpus", "PidsLimit")) or any(
                    type(x["Soft"]) is not int or type(x["Hard"]) is not int for x in host["Ulimits"]):
                raise ValueError("Docker numeric configuration is not strict")
            if (d["Id"] != cid or d["Name"] != "/" + instance["name"]
                    or config["Labels"].get("coding-agent-mastery-create-nonce") != instance["creation_nonce"]
                    or config["Labels"].get("coding-agent-mastery") != "disposable"
                    or d["Image"] != image["output"].decode().strip()
                    or config["User"] != POLICY["user"] or config["WorkingDir"] != POLICY["workdir"]
                    or config["Entrypoint"] != POLICY["entrypoint"] or config["Cmd"] != POLICY["command"]
                    or host["NetworkMode"] != "none" or host["ReadonlyRootfs"] is not True
                    or host["Privileged"] is not False or host.get("Binds") not in (None, [])
                    or d.get("Mounts") not in (None, []) or host["Memory"] != launch["memory_mb"] * 1048576
                    or host["MemorySwap"] != launch["memory_mb"] * 1048576
                    or host["NanoCpus"] != int(launch["cpus"] * 1000000000)
                    or host["PidsLimit"] != launch["pids"] or host["CapDrop"] != ["ALL"]
                    or host.get("CapAdd") not in (None, []) or host.get("Devices") not in (None, [])
                    or host.get("DeviceRequests") not in (None, []) or host.get("VolumesFrom") not in (None, [])
                    or host.get("PidMode", "") != "" or host.get("IpcMode", "private") != "private"
                    or host.get("UsernsMode", "") != "" or host.get("CgroupnsMode", "private") != "private"
                    or host.get("UTSMode", "") != "" or host.get("ExtraHosts") not in (None, [])
                    or host.get("PortBindings") not in (None, {}) or host.get("Links") not in (None, [])
                    or host["SecurityOpt"] != ["no-new-privileges"] or host["Tmpfs"] != expected_tmpfs
                    or host["LogConfig"]["Type"] != "none"
                    or ulimits != {k: (v, v) for k, v in POLICY["ulimits"].items()}):
                raise ValueError("Docker instance ownership/config mismatch")
        except (KeyError, ValueError, TypeError, UnicodeError) as error:
            raise RuntimeError("Docker instance ownership/config mismatch") from error
        self.confirm(self.backend)
        return cid

    def remove_owned(self, instance, *, before_remove=None):
        cid = instance["container_id"]
        ids = self.inventory(container_id=cid)
        if ids:
            self.inspect_owned(instance)
            self.confirm(self.backend)
            if before_remove is not None:
                before_remove()
            self.runner(["docker", "rm", "--force", cid], timeout=30, max_output=4096)
        if self.inventory(container_id=cid):
            raise RuntimeError("Docker retirement unconfirmed")
        self.confirm(self.backend)
        return cid


class EnvironmentLifecycle:
    def __init__(self, store, artifacts, tenant, task_id, sandbox_id, backend):
        if type(backend) is not DockerEnvironmentBackend:
            raise ValueError("explicit local Docker environment backend required")
        self.store, self.artifacts, self.tenant, self.task_id, self.sandbox_id = store, artifacts, tenant, task_id, sandbox_id
        self.backend = backend
        row = self.row()
        if row["task_id"] != task_id:
            raise ValueError("environment reservation outside task")

    def row(self):
        return self.store.read_environment_journal(self.tenant, self.sandbox_id)

    def source(self, *, purpose, tree_digest, input_digest, grader_digest, environment_digest):
        row = self.row()
        return validate_source({"generation": row["generation"], "service_incarnation": row["service_incarnation"],
                                "purpose": purpose, "tree_digest": tree_digest, "input_digest": input_digest,
                                "grader_digest": grader_digest, "environment_digest": environment_digest})

    def instance(self, *, ordinal, source, launch, max_instances):
        self.backend.confirm(self.backend.backend)
        grant = self.store.begin_environment_instance(self.tenant, self.sandbox_id, source=source,
            backend=self.backend.backend, max_instances=max_instances, ordinal=ordinal, launch=launch)
        return EnvironmentBinding(self, grant)

    def _observe(self, intent_id, kind, status, cid=None, diagnostic=""):
        row = self.row()
        journal = row["environment_journal"]
        self.backend.confirm(journal["backend"])
        instance = next((i for i in journal["instances"] if i["intent_id"] == intent_id), None)
        if instance is None:
            raise Conflict("environment intent not present")
        value = observation_value(journal, instance, kind, status, cid, diagnostic)
        key = "create_observation_ref" if kind == "create" else "retirement_observation_ref"
        old_ref = instance[key]
        if old_ref is not None and read_observation(self.artifacts, self.tenant, self.task_id, old_ref) == value:
            ref = old_ref
        else:
            ref = self.artifacts.put_json(self.tenant, self.task_id, validate_observation(value))
        method = self.store.bind_environment_instance if kind == "create" else self.store.record_environment_retirement
        return method(self.tenant, self.sandbox_id, intent_id, ref, expected_revision=journal["revision"])

    def close(self):
        known = self.row()
        if known["status"] == "retired":
            return self.store.retire_sandbox(self.tenant, self.sandbox_id, known["retirement_evidence"])
        self.store.request_environment_cleanup(self.tenant, self.sandbox_id)
        row = self.row()
        journal = row.get("environment_journal")
        if journal is None or any(i["state"] not in {"retired", "create_rejected"} for i in journal["instances"]):
            raise RuntimeError("environment cleanup unresolved; retain physical slot")
        # The store recognizes only this exact terminal journal identity as final evidence.
        evidence = {"kind": PROFILE, "sandbox_id": self.sandbox_id, "journal_digest": digest_json(journal)}
        return self.store.retire_sandbox(self.tenant, self.sandbox_id, evidence)


class EnvironmentBinding:
    def __init__(self, lifecycle, grant):
        self.lifecycle, self.grant = lifecycle, deepcopy(grant)
        self.instance = deepcopy(grant["instance"])

    def assert_execution(self):
        self.lifecycle.backend.confirm(self.lifecycle.backend.backend)
        actual = self.lifecycle.store.assert_environment_execution(self.lifecycle.tenant,
            self.lifecycle.sandbox_id, self.instance["intent_id"])
        if any(actual[k] != self.instance[k] for k in ("intent_id", "name", "creation_nonce", "launch", "container_id")):
            raise Conflict("environment binding differs from durable execution identity")
        return actual

    def bind(self, cid):
        candidate = deepcopy(self.instance)
        candidate["container_id"] = cid
        self.lifecycle.backend.inspect_owned(candidate)
        result = self.lifecycle._observe(self.instance["intent_id"], "create", "bound", cid)
        self.instance = deepcopy(result["instance"])
        return result

    def reject(self):
        return self.lifecycle._observe(self.instance["intent_id"], "create", "create_rejected", diagnostic="acknowledged_name_conflict")

    def close(self):
        row = self.lifecycle.row()
        journal = row["environment_journal"]
        instance = next(i for i in journal["instances"] if i["intent_id"] == self.instance["intent_id"])
        if instance["state"] in {"retired", "create_rejected"}:
            return {"retired": True, "container": instance["name"], "container_id": instance["container_id"],
                    "creation_nonce": instance["creation_nonce"], "evidence": "durable terminal environment observation"}
        try:
            self.lifecycle.store.assert_environment_cleanup(self.lifecycle.tenant, self.lifecycle.sandbox_id,
                                                            instance["intent_id"])
            self.lifecycle.backend.confirm(journal["backend"])
            if instance["container_id"] is None:
                ids = self.lifecycle.backend.inventory(nonce=instance["creation_nonce"])
                if len(ids) != 1:
                    raise RuntimeError("create_absence_is_unresolved")
                self.bind(ids[0])
                instance = self.instance
            cid = self.lifecycle.backend.remove_owned(instance, before_remove=lambda:
                self.lifecycle.store.assert_environment_cleanup(self.lifecycle.tenant, self.lifecycle.sandbox_id,
                                                                instance["intent_id"]))
            result = self.lifecycle._observe(instance["intent_id"], "retirement", "absent", cid)
            self.instance = deepcopy(result["instance"])
            return {"retired": True, "container": instance["name"], "container_id": cid,
                    "creation_nonce": instance["creation_nonce"], "evidence": "owned immutable ID absent on original daemon"}
        except Exception:
            # A sanitized diagnostic records uncertainty, never converts absence into proof.
            try:
                self.lifecycle._observe(instance["intent_id"], "retirement", "unresolved", instance["container_id"],
                                        "physical_cleanup_unresolved")
            except Exception:
                pass
            raise RuntimeError("environment cleanup unresolved; retain physical slot") from None


def reconcile_environment(lifecycle, docker_backend=None, *, max_instances=32):
    strict_int(max_instances, "reconciliation bound", 1, 32)
    if docker_backend is not None and docker_backend is not lifecycle.backend:
        raise ValueError("configured reconciliation backend mismatch")
    row = lifecycle.row()
    journal = row.get("environment_journal")
    if journal is None:
        return {"status": "unsupported", "sandbox_id": lifecycle.sandbox_id, "reason": "historical_nonce_not_recorded"}
    validate_journal(journal, lifecycle.sandbox_id, lifecycle.tenant, lifecycle.task_id)
    if len(journal["instances"]) > max_instances:
        raise ValueError("reconciliation instance bound exceeded")
    if journal["phase"] == "retired":
        return {"status": "retired", "sandbox_id": lifecycle.sandbox_id, "instances": len(journal["instances"])}
    lifecycle.store.request_environment_cleanup(lifecycle.tenant, lifecycle.sandbox_id)
    unresolved = []
    for instance in journal["instances"]:
        binding = EnvironmentBinding(lifecycle, {"duplicate": True, "revision": journal["revision"], "instance": instance})
        try:
            binding.close()
        except Exception:
            unresolved.append({"intent_id": instance["intent_id"], "container_id": instance["container_id"],
                               "reason": "physical_cleanup_unresolved"})
    if unresolved:
        return {"status": "unresolved", "sandbox_id": lifecycle.sandbox_id, "instances": unresolved}
    lifecycle.close()
    return {"status": "retired", "sandbox_id": lifecycle.sandbox_id, "instances": len(journal["instances"])}
