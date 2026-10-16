"""Closed configuration for the authored, offline fixture service."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from .admission import validate_admission_policy
from .api import Principal
from .artifacts import canonical_bytes, digest_json
from .contracts import freeze, parse_json, strict_int, timestamp, validate_contract
from .execution import tree_digest
from .verification import FixtureVerifier

CONFIG_CAP = 262144
LIMITS = {"service_slot_limit", "tenant_slot_limit", "service_budget_units", "tenant_budget_units"}


def closed(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("invalid " + label)


def safe_path(value, *, directory=False):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(char) < 32 or char in "?#" for char in value)):
        raise ValueError("invalid local path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("absolute canonical local path required")
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symlink local path is unsupported")
        if part != path or directory:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("local directory required")
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular unlinked local file required")
    return path


def read_json_file(path, *, max_bytes=CONFIG_CAP):
    path = safe_path(str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > max_bytes:
            raise ValueError("invalid bounded configuration file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("configuration file exceeds limit")
        return parse_json(data)
    finally:
        os.close(fd)


def fixture_contract(workload, execution_deadline, review_deadline):
    from workloads import load_task, validate_assets
    from workloads.registry import TARGET_FILES
    if timestamp(execution_deadline, "execution_deadline") <= 0 or timestamp(review_deadline, "review_deadline") <= 0:
        raise ValueError("positive explicit deadlines required")
    validate_assets()
    selected = load_task(workload)
    files = {p: (selected.baseline_path / p).read_text() for p in TARGET_FILES}
    return validate_contract({
        "repo_id": "synthetic-issue-tracker:" + selected.task_id,
        "base_revision": tree_digest(files), "requirements": list(selected.requirements),
        "capabilities": ["read_file", "search", "replace_text", "run_tests", "finish"],
        "execution_deadline": timestamp(execution_deadline, "execution_deadline"),
        "review_deadline": timestamp(review_deadline, "review_deadline"),
        "profile": "production", "patch_slot_limit": 2, "budget_units": 1000,
        "max_nodes": 8, "max_attempts": 8, "model": "scripted-fixture-v1",
        "grader_digest": selected.as_dict()["grader_sha256"],
        "environment_digest": FixtureVerifier.environment_digest,
    }, now=0)


def validate_config(value):
    closed(value, {"schema", "mode", "root", "host", "port", "limits", "admission_policy",
                   "worker", "principals", "catalog"}, "serving config")
    if type(value["schema"]) is not int or value["schema"] != 1 or value["mode"] != "offline_fixture_v1":
        raise ValueError("unsupported serving mode")
    if len(canonical_bytes(value)) > CONFIG_CAP:
        raise ValueError("serving config exceeds limit")
    safe_path(value["root"], directory=True)
    if value["host"] not in {"127.0.0.1", "::1"}:
        raise ValueError("literal loopback host required")
    strict_int(value["port"], "port", 1024, 65535)
    closed(value["limits"], LIMITS, "operating limits")
    for key, item in value["limits"].items():
        strict_int(item, key, 3 if key.endswith("slot_limit") else 1000, 10000 if key.endswith("slot_limit") else 2**63-1)
    validate_admission_policy(value["admission_policy"])
    closed(value["worker"], {"poll_ms", "shutdown_seconds"}, "worker limits")
    strict_int(value["worker"]["poll_ms"], "poll_ms", 100, 10000)
    strict_int(value["worker"]["shutdown_seconds"], "shutdown_seconds", 1, 120)
    catalog = value["catalog"]
    if not isinstance(catalog, list) or not 1 <= len(catalog) <= 64:
        raise ValueError("bounded fixture catalog required")
    repos = set()
    for item in catalog:
        if not isinstance(item, dict) or not isinstance(item.get("repo_id"), str):
            raise ValueError("invalid fixture contract")
        repo = item["repo_id"]
        if not repo.startswith("synthetic-issue-tracker:") or repo in repos:
            raise ValueError("unknown or duplicate fixture contract")
        try:
            expected = fixture_contract(repo.split(":", 1)[1], item["execution_deadline"], item["review_deadline"])
        except (KeyError, TypeError) as exc:
            raise ValueError("unknown fixture contract") from exc
        if canonical_bytes(item) != canonical_bytes(expected):
            raise ValueError("fixture contract differs from supported catalog")
        repos.add(repo)
    principals = value["principals"]
    if not isinstance(principals, list) or not 1 <= len(principals) <= 32:
        raise ValueError("explicit bounded principals required")
    identities, names = set(), set()
    for entry in principals:
        closed(entry, {"tenant_id", "subject_id", "repositories", "can_review", "profiles", "token_env"}, "principal")
        for key in ("repositories", "profiles"):
            if not isinstance(entry[key], list) or not entry[key] or any(type(x) is not str for x in entry[key]):
                raise ValueError("principal grants must be lists of strings")
            if len(set(entry[key])) != len(entry[key]):
                raise ValueError("duplicate principal grant")
        principal = principal_value(entry)
        if not principal.repositories <= repos or principal.profiles != frozenset({"production"}):
            raise ValueError("principal grants outside offline catalog")
        name = entry["token_env"]
        if not isinstance(name, str) or not re.fullmatch(r"CAM_SERVE_TOKEN_[A-Z0-9_]{1,64}", name):
            raise ValueError("invalid token environment name")
        identity = (principal.tenant_id, principal.subject_id)
        if identity in identities or name in names:
            raise ValueError("duplicate principal identity or credential source")
        identities.add(identity)
        names.add(name)
    return freeze(value)


def principal_value(entry):
    return Principal(entry["tenant_id"], entry["subject_id"], frozenset(entry["repositories"]),
                     entry["can_review"], frozenset(entry["profiles"]))


def load_tokens(config, environ):
    tokens = {}
    for entry in config["principals"]:
        token = environ.get(entry["token_env"])
        if not isinstance(token, str) or not 24 <= len(token) <= 512 or token in tokens:
            raise ValueError("missing, duplicate or invalid serving credential")
        tokens[token] = principal_value(entry)
    return tokens


def config_identity(config):
    return digest_json(config)
