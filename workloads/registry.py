"""Data-only candidate inspection and explicit trusted oracle controls.

No candidate import, subprocess, shell command, patch command, or eval occurs
here. Frozen author-created control source can execute only by an explicit
trusted_control_report call after its identity is checked. That call is a local
fixture test, never an isolation/candidate-capability claim.
"""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
import stat
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "manifests" / "tasks.json"
LOCK_PATH = ROOT / "manifests" / "assets.lock.json"
TARGET_FILES = ("client.py", "issue_tracker.py")
MAX_CANDIDATE_BYTES = 262144


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def tree_digest(directory: str | Path, files: tuple[str, ...] = TARGET_FILES) -> str:
    """Content identity: SHA256 of canonical [relative-name, byte-sha256] pairs.

    This is a content identity, not an invented Git revision. Other service
    components must use this same algorithm or record a distinct identity kind.
    """
    root = Path(directory)
    pairs = []
    for name in sorted(files):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("tree filenames must be relative and contained")
        path = root / relative
        if path.is_symlink() or not path.is_file() or root.resolve() not in path.resolve().parents:
            raise ValueError("tree file is absent or escapes root")
        pairs.append([name, _sha(path.read_bytes())])
    return _sha(_canonical(pairs))


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    split: str
    tier: str
    template_group: str
    baseline_id: str
    baseline_digest: str
    definition_digest: str
    requirements: tuple[str, ...]
    variant: int
    deadline_seconds: int

    @property
    def baseline_path(self) -> Path:
        return ROOT / "baseline" / self.baseline_id

    @property
    def expected_patch_path(self) -> Path:
        return ROOT / "oracle" / "patches" / f"{self.baseline_id}.patch"

    def as_dict(self) -> dict[str, Any]:
        return dict(_task_record(self.task_id))


def _registry() -> dict[str, Any]:
    content = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if content.get("schema_version") != 1:
        raise ValueError("unsupported workload registry schema")
    return content


def _task_record(task_id: str) -> dict[str, Any]:
    for row in _registry()["tasks"]:
        if row["task_id"] == task_id:
            return row
    raise KeyError(task_id)


def _definition(row: dict[str, Any]) -> TaskDefinition:
    return TaskDefinition(
        row["task_id"], row["split"], row["tier"], row["template_group"],
        row["baseline_id"], row["baseline_digest"], row["definition_digest"],
        tuple(row["requirements"]), row["variant"], row["deadline_seconds"],
    )


def list_tasks(*, split: str | None = None, tier: str | None = None) -> tuple[TaskDefinition, ...]:
    return tuple(_definition(row) for row in _registry()["tasks"]
                 if (split is None or row["split"] == split) and (tier is None or row["tier"] == tier))


def load_task(task_id: str) -> TaskDefinition:
    return _definition(_task_record(task_id))


def validate_assets() -> dict[str, Any]:
    """Check lock, grader, exact bases, patches, controls and manifest identities.

    The lock is an integrity reference under verifier authority, not protection
    against a privileged author rewriting source AND lock. A Linux deployment
    must mount this root read-only outside candidate write authority.
    """
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("unsupported asset lock schema")
    for relative, expected in lock["files"].items():
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or ROOT not in path.resolve().parents:
            raise ValueError(f"missing/unsafe frozen asset: {relative}")
        if _sha(path.read_bytes()) != expected:
            raise ValueError(f"frozen asset hash mismatch: {relative}")
    registry = _registry()
    identifiers = set()
    for row in registry["tasks"]:
        task = _definition(row)
        if task.task_id in identifiers:
            raise ValueError("duplicate task identity")
        identifiers.add(task.task_id)
        specification = dict(row)
        specification.pop("definition_digest")
        if task.definition_digest != _sha(_canonical(specification)):
            raise ValueError("task definition digest mismatch")
        if tree_digest(task.baseline_path) != task.baseline_digest:
            raise ValueError("task baseline digest mismatch")
        if _sha(task.expected_patch_path.read_bytes()) != row["reference_patch_sha256"]:
            raise ValueError("reference patch digest mismatch")
        incorrect = ROOT / "oracle" / "patches" / f"{task.baseline_id}.incorrect.patch"
        if _sha(incorrect.read_bytes()) != row["incorrect_patch_sha256"]:
            raise ValueError("incorrect control patch digest mismatch")
        if tree_digest(ROOT / "oracle" / "incorrect" / task.baseline_id) != row["incorrect_tree_digest"]:
            raise ValueError("incorrect control tree digest mismatch")
        if row["grader_sha256"] != lock["files"]["oracle/fixtures/acceptance.py"]:
            raise ValueError("task grader identity mismatch")
    return {"valid": True, "tasks": len(identifiers), "files": len(lock["files"]),
            "registry_sha256": _sha(REGISTRY_PATH.read_bytes()),
            "asset_lock_sha256": _sha(LOCK_PATH.read_bytes()),
            "provenance": "AI-authored synthetic templates; one repository family"}


def materialize_task(task: str | TaskDefinition, destination: str | Path) -> Path:
    """Copy only developer-visible target files into a fresh disposable root."""
    selected = load_task(task if isinstance(task, str) else task.task_id)
    validate_assets()
    destination = Path(destination)
    # Refuse existing destinations: no overwriting user work or frozen assets.
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    try:
        for name in TARGET_FILES:
            shutil.copyfile(selected.baseline_path / name, destination / name)
        visible = selected.as_dict()["visible_spec"]
        (destination / "TASK.json").write_text(json.dumps(visible, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


def inspect_candidate(task: str | TaskDefinition, candidate_root: str | Path) -> dict[str, Any]:
    """Bounded source/AST checks ONLY. A successful result is not a verifier pass.

    Candidate workspace writes to protected assets are impossible only under an
    external OS boundary. Locally this function detects frozen-asset changes.
    Inspection does not contain concurrent adversarial workspace mutations.
    """
    selected = load_task(task if isinstance(task, str) else task.task_id)
    try:
        validate_assets()
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return {"status": "grader_integrity_failed", "verified": False,
                "mode": "static_only_no_execution", "detail": str(error)}
    root = Path(candidate_root)
    if not root.is_dir() or root.is_symlink():
        return {"status": "candidate_invalid", "verified": False,
                "mode": "static_only_no_execution", "detail": "candidate must be a directory"}
    problems = []
    total = 0
    observed = set()
    # All declared files are top-level, so do not recurse into candidate dirs.
    for index, path in enumerate(root.iterdir()):
        if index >= 128:
            problems.append("candidate entry limit exceeded")
            break
        entry = path.lstat()
        if stat.S_ISLNK(entry.st_mode):
            problems.append(f"symlink rejected: {path.relative_to(root)}")
        elif stat.S_ISDIR(entry.st_mode):
            problems.append(f"undeclared directory: {path.relative_to(root)}")
        elif stat.S_ISREG(entry.st_mode):
            name = str(path.relative_to(root))
            observed.add(name)
            if name not in {*TARGET_FILES, "TASK.json"}:
                problems.append(f"undeclared path: {name}")
            total += entry.st_size
            if total > MAX_CANDIDATE_BYTES:
                problems.append("candidate byte limit exceeded")
                break
        else:
            problems.append(f"nonregular entry rejected: {path.relative_to(root)}")
    if total > MAX_CANDIDATE_BYTES:
        problems.append("candidate byte limit exceeded")
    if not set(TARGET_FILES).issubset(observed):
        problems.append("required target file missing")
    if not problems:
        for name in TARGET_FILES:
            try:
                source = (root / name).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=name)
                compile(tree, name, "exec")  # compile does NOT execute code.
            except (ValueError, SyntaxError, UnicodeError, OSError, RecursionError) as error:
                problems.append(f"{name}: {type(error).__name__}: {error}")
    return {"status": "candidate_invalid" if problems else "pending_linux_verification",
            "verified": False, "mode": "static_only_no_execution", "task_id": selected.task_id,
            "task_definition_digest": selected.definition_digest,
            "baseline_digest": selected.baseline_digest,
            "candidate_digest": tree_digest(root) if not problems else None,
            "problems": problems,
            "limitation": "syntax/integrity checks do not establish behavioral correctness or isolation"}


def _trusted_module(relative: str) -> types.ModuleType:
    """Private loader accepts ONLY paths already pinned in the frozen lock."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if relative not in lock["files"] or not relative.endswith(".py"):
        raise ValueError("not a pinned trusted control")
    source = (ROOT / relative).read_bytes()
    if _sha(source) != lock["files"][relative]:
        raise ValueError("control integrity mismatch")
    module = types.ModuleType("trusted_workload_control")
    module.__file__ = str(ROOT / relative)
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def trusted_control_report(task: str | TaskDefinition) -> dict[str, Any]:
    """Run authored known-good/bad controls, never a supplied candidate root.

    This is explicitly a trusted fixture host test. Behavioral execution of
    arbitrary candidate code belongs exclusively to the Linux runner boundary.
    """
    selected = load_task(task if isinstance(task, str) else task.task_id)
    validate_assets()
    grader = _trusted_module("oracle/fixtures/acceptance.py")
    paths = {
        "unchanged": f"baseline/{selected.baseline_id}",
        "correct": "oracle/reference",
        "plausible_incorrect": f"oracle/incorrect/{selected.baseline_id}",
    }
    controls = {}
    for kind, root in paths.items():
        tracker = _trusted_module(f"{root}/issue_tracker.py")
        client = _trusted_module(f"{root}/client.py")
        controls[kind] = grader.grade(selected.requirements, tracker, client, selected.variant)
        controls[kind]["tree_digest"] = tree_digest(ROOT / root)
    controls_valid = (not controls["unchanged"]["passed"] and controls["correct"]["passed"]
                      and not controls["plausible_incorrect"]["passed"])
    return {"task_id": selected.task_id, "controls_valid": controls_valid,
            "mode": "trusted_author_fixture_host_execution", "controls": controls,
            "task_definition_digest": selected.definition_digest,
            "asset_lock_sha256": _sha(LOCK_PATH.read_bytes()),
            "independent_reproduction": "pending",
            "limitation": "local authored controls do not prove candidate containment or grader completeness"}


def linux_runner_request(task: str | TaskDefinition, candidate_root: str | Path, *,
                         image_digest: str, architecture: str = "linux/amd64",
                         cpu_seconds: int = 30, memory_bytes: int = 268435456,
                         process_limit: int = 16, disk_bytes: int = 16777216,
                         output_bytes: int = 65536, wall_seconds: int = 60) -> dict[str, Any]:
    """Prepare a data-only external runner request; it launches nothing.

    Caller MUST choose an actually available pinned image and enforce the
    deployment contract. Provider/model/run budgets remain separate/unselected.
    """
    selected = load_task(task if isinstance(task, str) else task.task_id)
    inspection = inspect_candidate(selected, candidate_root)
    if inspection["status"] != "pending_linux_verification":
        raise ValueError("candidate has not passed static admission")
    digest = image_digest.removeprefix("sha256:") if isinstance(image_digest, str) else ""
    if not isinstance(image_digest, str) or not image_digest.startswith("sha256:") or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("image digest must be pinned sha256:<64 lowercase hex>")
    if architecture not in ("linux/amd64", "linux/arm64"):
        raise ValueError("unsupported Linux architecture")
    limits = dict(cpu_seconds=cpu_seconds, memory_bytes=memory_bytes, process_limit=process_limit,
                  disk_bytes=disk_bytes, output_bytes=output_bytes, wall_seconds=wall_seconds)
    if any(type(value) is not int or value <= 0 for value in limits.values()):
        raise ValueError("runner limits must be positive integers")
    return {"schema_version": 1, "execution_state": "not_executed", "task_id": selected.task_id,
            "task_definition_digest": selected.definition_digest,
            "candidate_digest": inspection["candidate_digest"],
            "baseline_digest": selected.baseline_digest,
            "image_digest": image_digest, "architecture": architecture,
            "candidate_mount": {"source": str(Path(candidate_root).resolve()), "target": "/candidate", "mode": "read_only"},
            "grader_mount": {"source": str(ROOT / "oracle" / "fixtures"), "target": "/grader", "mode": "read_only"},
            "grader_sha256": selected.as_dict()["grader_sha256"],
            "asset_lock_sha256": _sha(LOCK_PATH.read_bytes()),
            "requirements": list(selected.requirements), "variant": selected.variant,
            "limits": limits, "network": "disabled", "credentials": "none",
            "python": ">=3.11", "dependency_lock": "stdlib-only-v1",
            "receipt_channel": "external_supervisor_owned",
            "grader_process_boundary": "trusted supervisor must not import candidate code into its own interpreter; use an isolated worker protocol adapter",
            "runner_implementation_status": "contract_only_not_implemented",
            "enforcement_required": ["isolated Linux environment", "read-only grader assets",
                                     "no host/service credentials", "bounded writable scratch",
                                     "candidate cannot share verifier interpreter or receipt authority",
                                     "PID/CPU/RAM/disk/output/time enforcement",
                                     "supervisor-authenticated digest-bound result"]}
