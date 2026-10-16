#!/usr/bin/env python3
"""Freeze, build and install a curated local candidate without network access.

The manifest is the authorization boundary. Discovery proposes an exact list at
freeze time; build rejects additions, removals and changed bytes. Runtime code is
never imported in the builder process. All product execution is installed Python.
"""
from __future__ import annotations

import argparse
import ast
import email.parser
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tarfile
import tomllib
import zipfile


class ReleaseError(RuntimeError):
    """A failed release boundary; partial diagnostics must not become success."""


PRODUCTS = ("service", "evals", "compute", "workloads")
SKILL_ASSETS = frozenset({
    "workloads/skills/verified-repair-guide/SKILL.md",
    "workloads/skills/verified-repair-guide/references/checklist.md",
    "workloads/skills/verified-repair-guide/assets/example.json",
})
FIXED = {
    "pyproject.toml": "pyproject.toml",
    "uv.lock": "uv.lock",
    "README.md": "release/README.md",
    "LICENSE": "release/LICENSE",
    "NOTICE": "release/NOTICE",
    "release/README.md": "release/README.md",
    "release/LICENSE": "release/LICENSE",
    "release/NOTICE": "release/NOTICE",
    "release/OFFLINE.md": "release/OFFLINE.md",
    "release/acceptance/installed_package_acceptance.py": "release/acceptance/installed_package_acceptance.py",
    "scripts/build_offline_release.py": "scripts/build_offline_release.py",
    **{path: path for path in SKILL_ASSETS},
}
FORBIDDEN_PARTS = {
    "__pycache__", ".git", ".venv", "venv", "tests", "research", "references",
    "context", "study", "archive", "runs", "control-inputs", "node_modules",
    "build", "dist", ".cache",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def path_name(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ReleaseError(f"unsafe relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {"", ".", ".."} for p in path.parts):
        raise ReleaseError(f"unsafe relative path: {value!r}")
    if any((p in FORBIDDEN_PARTS and not (p == "references" and value in SKILL_ASSETS))
           or p.startswith(".env") for p in path.parts):
        raise ReleaseError(f"forbidden release path: {value!r}")
    if path.suffix in {".pyc", ".pyo"}:
        raise ReleaseError(f"forbidden bytecode: {value!r}")
    return value


def regular(root: Path, relative: str) -> Path:
    path_name(relative)
    root = root.absolute()
    # Resolve nothing until every parent has been checked: aliases are rejected.
    for parent in [root, *root.parents]:
        if parent.is_symlink():
            raise ReleaseError(f"symlink source parent: {parent}")
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise ReleaseError(f"missing selected input: {relative}") from exc
        if stat.S_ISLNK(mode):
            raise ReleaseError(f"symlink selected input: {relative}")
        if current != root / relative and not stat.S_ISDIR(mode):
            raise ReleaseError(f"non-directory input parent: {relative}")
    if not stat.S_ISREG(mode):
        raise ReleaseError(f"nonregular selected input: {relative}")
    return current


def identity(path: Path) -> dict:
    data = path.read_bytes()
    return {"sha256": digest(data), "size": len(data)}


def runtime_asset(name: str) -> bool:
    if name in SKILL_ASSETS:
        return True
    parts = PurePosixPath(name).parts
    if parts[0] not in PRODUCTS:
        return False
    if name.endswith(".py"):
        return True
    if parts[0] == "workloads" and len(parts) > 2:
        return (parts[1] in {"manifests", "evidence", "repair"} and name.endswith(".json")) or (
            parts[1] == "oracle" and name.endswith(".patch")
        )
    return False


def discover(root: Path) -> dict[str, str]:
    selected = dict(FIXED)
    for product in PRODUCTS:
        directory = root / product
        if not directory.is_dir() or directory.is_symlink():
            raise ReleaseError(f"missing or aliased product directory: {product}")
        for current, directories, names in os.walk(directory, followlinks=False):
            for directory_name in list(directories):
                path = Path(current) / directory_name
                if path.is_symlink():
                    raise ReleaseError(f"symlink product directory: {path.relative_to(root)}")
            directories[:] = [d for d in directories if d not in FORBIDDEN_PARTS and not d.startswith(".")]
            for name in names:
                path = Path(current) / name
                relative = path.relative_to(root).as_posix()
                if runtime_asset(relative):
                    regular(root, relative)
                    selected[relative] = relative
    for target, origin in selected.items():
        path_name(target)
        regular(root, origin)
    check_standalone_script(regular(root, FIXED["release/acceptance/installed_package_acceptance.py"]))
    return dict(sorted(selected.items()))


def check_standalone_script(path: Path) -> None:
    tree = ast.parse(path.read_text())
    def is_sys_path(node):
        return (isinstance(node, ast.Attribute) and node.attr == "path"
                and isinstance(node.value, ast.Name) and node.value.id == "sys")

    for node in ast.walk(tree):
        imported = []
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        if any(name.split(".")[0] in {"tests", "runpy"} for name in imported):
            raise ReleaseError("acceptance script depends on checkout tests/runpy")
        if is_sys_path(node) and isinstance(node.ctx, (ast.Store, ast.Del)):
            raise ReleaseError("acceptance script mutates sys.path")
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if any(is_sys_path(child) for child in ast.walk(node.value)):
                raise ReleaseError("acceptance script mutates sys.path")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and is_sys_path(node.func.value):
            raise ReleaseError("acceptance script calls a sys.path method")


def check_output(root: Path, output: Path, selected: dict[str, str]) -> None:
    output = output.absolute()
    for parent in [output, *output.parents]:
        if parent.is_symlink():
            raise ReleaseError(f"symlink output parent: {parent}")
    if output.exists():
        raise ReleaseError(f"output collision: {output}")
    for relative in set(selected.values()):
        source = (root / relative).absolute()
        if source == output or output in source.parents:
            raise ReleaseError(f"output overlaps selected input: {relative}")


def freeze(root: Path, output: Path) -> dict:
    selected = discover(root)
    check_output(root, output, selected)
    project = tomllib.loads(regular(root, "pyproject.toml").read_text())["project"]
    manifest = {
        "schema": 1,
        "project": {"name": project["name"], "version": project["version"]},
        "files": {target: {"origin": origin, **identity(regular(root, origin))}
                  for target, origin in selected.items()},
        "archive_generated_members": ["META/frozen-manifest.json"],
        "platform": {"python": platform.python_version(), "system": platform.system(),
                     "machine": platform.machine()},
    }
    manifest["content_sha256"] = digest(canonical(manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, manifest, exclusive=True)
    return manifest


def no_duplicates(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), dict):
        raise ReleaseError("unsupported manifest schema")
    claim = manifest.get("content_sha256")
    payload = {k: v for k, v in manifest.items() if k != "content_sha256"}
    if claim != digest(canonical(payload)):
        raise ReleaseError("manifest identity mismatch")
    for target, record in manifest["files"].items():
        path_name(target)
        path_name(record["origin"])
        if not SHA.fullmatch(record.get("sha256", "")) or type(record.get("size")) is not int:
            raise ReleaseError(f"malformed file identity: {target}")
    if manifest.get("archive_generated_members") != ["META/frozen-manifest.json"]:
        raise ReleaseError("unexpected generated archive members")
    return manifest


def check_sources(root: Path, manifest: dict) -> None:
    selected = discover(root)
    frozen = {target: record["origin"] for target, record in manifest["files"].items()}
    if selected != frozen:
        raise ReleaseError(f"allowlist changed: added={sorted(selected.keys() - frozen.keys())}; "
                           f"removed={sorted(frozen.keys() - selected.keys())}")
    for target, record in manifest["files"].items():
        if identity(regular(root, record["origin"])) != {k: record[k] for k in ("sha256", "size")}:
            raise ReleaseError(f"source drift: {target}")


def write_json(path: Path, value: object, *, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")


def clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTHON", "UV_", "PIP_")) and key != "VIRTUAL_ENV"}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", UV_LINK_MODE="copy")
    return env


def run(command: list[str], cwd: Path, log: Path) -> str:
    result = subprocess.run(command, cwd=cwd, env=clean_env(), text=True, capture_output=True, check=False)
    write_json(log, {"command": command, "cwd": str(cwd), "returncode": result.returncode,
                     "stdout": result.stdout, "stderr": result.stderr}, exclusive=True)
    if result.returncode:
        raise ReleaseError(f"command failed ({result.returncode}); diagnostics: {log}")
    return result.stdout


def export_requirements(lock_path: Path, project_name: str) -> tuple[str, dict]:
    # The packaging tool's marker implementation is part of the recorded backend
    # environment, not a product runtime requirement or a resolver refresh.
    from packaging.markers import Marker, default_environment

    lock = tomllib.loads(lock_path.read_text())
    packages: dict[str, list] = {}
    for package in lock["package"]:
        packages.setdefault(package["name"], []).append(package)
    projects = packages.get(project_name, [])
    if len(projects) != 1 or projects[0].get("source") != {"editable": "."}:
        raise ReleaseError("unsupported project lock identity")
    selected = {}
    seen = set()
    queue = list(projects[0].get("dependencies", []))
    marker_env = default_environment()
    while queue:
        requirement = queue.pop()
        try:
            if requirement.get("marker") and not Marker(requirement["marker"]).evaluate(marker_env):
                continue
        except Exception as exc:
            raise ReleaseError("unsupported lock marker") from exc
        name = requirement["name"]
        extras = tuple(sorted(requirement.get("extra", [])))
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        candidates = packages.get(name, [])
        if len(candidates) != 1:
            raise ReleaseError(f"unsupported lock version branch: {name}")
        package = candidates[0]
        if package.get("source") != {"registry": "https://pypi.org/simple"}:
            raise ReleaseError(f"unsupported dependency source: {name}")
        if requirement.get("version", package["version"]) != package["version"]:
            raise ReleaseError(f"lock version reference mismatch: {name}")
        hashes = sorted({w["hash"] for w in package.get("wheels", [])})
        if not hashes or any(not h.startswith("sha256:") or not SHA.fullmatch(h[7:]) for h in hashes):
            raise ReleaseError(f"missing supported binary wheel hashes: {name}")
        selected[name] = {"version": package["version"], "hashes": hashes,
                          "wheels": [{"filename": PurePosixPath(w["url"]).name,
                                      "sha256": w["hash"][7:], "size": w["size"]}
                                     for w in package["wheels"]]}
        queue.extend(package.get("dependencies", []))
        for extra in extras:
            if extra not in package.get("optional-dependencies", {}):
                raise ReleaseError(f"unsupported lock extra: {name}[{extra}]")
            queue.extend(package["optional-dependencies"][extra])
    lines = [name + "==" + record["version"] + " " + " ".join("--hash=" + h for h in record["hashes"])
             for name, record in sorted(selected.items())]
    return "\n".join(lines) + "\n", {"packages": dict(sorted(selected.items())), "marker_environment": marker_env,
                                       "project_extras": [], "lock": identity(lock_path)}


def stage_sources(root: Path, stage: Path, manifest: dict) -> None:
    stage.mkdir()
    for target, record in manifest["files"].items():
        data = regular(root, record["origin"]).read_bytes()
        if digest(data) != record["sha256"] or len(data) != record["size"]:
            raise ReleaseError(f"source drift while staging: {target}")
        destination = stage / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def source_archive(stage: Path, output: Path, manifest: dict) -> None:
    with output.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for target in sorted(manifest["files"]):
                data = regular(stage, target).read_bytes()
                header = tarfile.TarInfo(target)
                header.size = len(data)
                header.mode = 0o644
                archive.addfile(header, io.BytesIO(data))
            data = json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n"
            header = tarfile.TarInfo("META/frozen-manifest.json")
            header.size = len(data)
            header.mode = 0o644
            archive.addfile(header, io.BytesIO(data))


def validate_archive(path: Path, manifest: dict) -> dict:
    expected = set(manifest["files"]) | set(manifest["archive_generated_members"])
    found = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = path_name(member.name)
            if name in found or not member.isfile():
                raise ReleaseError(f"duplicate or nonregular archive member: {name}")
            found.add(name)
            data = archive.extractfile(member).read()
            if name == "META/frozen-manifest.json":
                if json.loads(data, object_pairs_hook=no_duplicates) != manifest:
                    raise ReleaseError("archive manifest mismatch")
            elif name not in manifest["files"] or identity_bytes(data) != {
                k: manifest["files"][name][k] for k in ("sha256", "size")
            }:
                raise ReleaseError(f"unexpected or changed archive member: {name}")
            if member.mode != 0o644 or member.uid != 0 or member.gid != 0 or member.mtime != 0:
                raise ReleaseError(f"unexpected archive metadata: {name}")
    if found != expected:
        raise ReleaseError("source archive inventory mismatch")
    return {**identity(path), "members": sorted(found), "metadata": "regular;0644;uid/gid/mtime=0"}


def identity_bytes(data: bytes) -> dict:
    return {"sha256": digest(data), "size": len(data)}


def wheel_inventory(path: Path, manifest: dict) -> dict:
    expected = {target for target in manifest["files"] if runtime_asset(target)}
    found = {}
    with zipfile.ZipFile(path) as wheel:
        for member in wheel.infolist():
            name = path_name(member.filename)
            kind = (member.external_attr >> 16) & 0o170000
            if member.is_dir() or kind not in {0, stat.S_IFREG} or name in found:
                raise ReleaseError(f"duplicate or nonregular wheel member: {name}")
            found[name] = identity_bytes(wheel.read(member))
        roots = {PurePosixPath(name).parts[0] for name in found if ".dist-info/" in name}
        if len(roots) != 1:
            raise ReleaseError("wheel must contain exactly one distribution")
        metadata_root = roots.pop()
        metadata = email.parser.BytesParser().parsebytes(wheel.read(metadata_root + "/METADATA"))
        if metadata["Name"] != manifest["project"]["name"] or metadata["Version"] != manifest["project"]["version"]:
            raise ReleaseError("stale wheel package identity")
        allowed_metadata = {metadata_root + "/" + name for name in (
            "METADATA", "WHEEL", "RECORD", "entry_points.txt", "top_level.txt", "licenses/LICENSE", "licenses/NOTICE",
        )}
        if set(found) - allowed_metadata != expected:
            raise ReleaseError(f"wheel source/asset inventory mismatch: "
                               f"missing={sorted(expected-set(found))}; "
                               f"extra={sorted(set(found)-expected-allowed_metadata)}")
        for name in expected:
            if found[name] != {k: manifest["files"][name][k] for k in ("sha256", "size")}:
                raise ReleaseError(f"stale wheel bytes: {name}")
        for notice in ("LICENSE", "NOTICE"):
            if found.get(metadata_root + "/licenses/" + notice) != {
                k: manifest["files"][notice][k] for k in ("sha256", "size")
            }:
                raise ReleaseError(f"wheel missing original license/notice: {notice}")
    return {**identity(path), "filename": path.name, "members": found}


def toolchain() -> dict:
    result = {"python": {"version": platform.python_version(), "executable": str(Path(sys.executable).absolute()),
                          "binary": identity(Path(sys.executable).resolve())},
              "platform": {"system": platform.system(), "machine": platform.machine()}, "distributions": {}}
    for name in ("setuptools", "pip", "packaging"):
        dist = importlib.metadata.distribution(name)
        files = {str(p): identity(Path(dist.locate_file(p))) for p in dist.files or []
                 if str(p).endswith((".py", "METADATA", "WHEEL")) and Path(dist.locate_file(p)).is_file()}
        result["distributions"][name] = {"version": dist.version, "files_sha256": digest(canonical(files))}
    result["build_backend"] = "setuptools.build_meta"
    return result


def build(root: Path, manifest_path: Path, output: Path) -> dict:
    manifest = load_manifest(manifest_path)
    check_sources(root, manifest)
    check_output(root, output, {k: r["origin"] for k, r in manifest["files"].items()})
    output.mkdir(parents=True)
    try:
        write_json(output / "frozen-manifest.json", manifest, exclusive=True)
        record = {"status": "building", "manifest": identity(manifest_path), "toolchain": toolchain()}
        stage = output / "stage"
        stage_sources(root, stage, manifest)
        check_sources(root, manifest)
        requirements, closure = export_requirements(stage / "uv.lock", manifest["project"]["name"])
        (output / "requirements-base.txt").write_text(requirements)
        write_json(output / "dependency-closure.json", closure, exclusive=True)
        archive = output / "source.tar.gz"
        source_archive(stage, archive, manifest)
        wheel_dir = output / "dist"
        wheel_dir.mkdir()
        run([sys.executable, "-I", "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index",
             "--no-cache-dir", "--wheel-dir", str(wheel_dir.absolute()), str(stage.absolute())],
            stage, output / "build-command.json")
        wheels = list(wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise ReleaseError("build did not produce exactly one wheel")
        record["wheel"] = wheel_inventory(wheels[0], manifest)
        record["archive"] = validate_archive(archive, manifest)
        for target, item in manifest["files"].items():
            if identity(regular(stage, target)) != {k: item[k] for k in ("sha256", "size")}:
                raise ReleaseError(f"staged source drift: {target}")
        check_sources(root, manifest)
        record.update(status="built", source_before_after="unchanged", requirements=identity(output / "requirements-base.txt"),
                      closure=identity(output / "dependency-closure.json"),
                      claims={"installed_acceptance": False, "published": False, "network": False})
        write_json(output / "build-evidence.json", record, exclusive=True)
        return record
    except Exception as exc:
        write_json(output / "build-failure.json", {"status": "failed", "error": str(exc)}, exclusive=True)
        raise


def verify_wheelhouse(directory: Path, closure: dict) -> dict:
    from packaging.tags import sys_tags
    from packaging.utils import canonicalize_name, parse_wheel_filename

    tags = set(sys_tags())
    records = {}
    allowed = {w["filename"]: (name, w) for name, p in closure["packages"].items() for w in p["wheels"]}
    selected = set()
    for wheel in directory.iterdir():
        if wheel.name not in allowed or not wheel.name.endswith(".whl"):
            raise ReleaseError(f"unexpected dependency material: {wheel.name}")
        regular(directory, wheel.name)
        name, expected = allowed[wheel.name]
        actual = identity(wheel)
        if actual != {k: expected[k] for k in ("sha256", "size")}:
            raise ReleaseError(f"dependency wheel hash mismatch: {wheel.name}")
        wheel_name, version, _, wheel_tags = parse_wheel_filename(wheel.name)
        if canonicalize_name(name) != wheel_name or str(version) != closure["packages"][name]["version"]:
            raise ReleaseError(f"dependency wheel identity mismatch: {wheel.name}")
        if tags & wheel_tags:
            selected.add(name)
        records[wheel.name] = actual
    missing = set(closure["packages"]) - selected
    if missing:
        raise ReleaseError(f"missing compatible locked binary wheels: {sorted(missing)}")
    return records


PROBE = r'''
import hashlib, importlib, importlib.metadata as m, json, pathlib, platform, sys
modules = ["service", "service.cli", "service.context", "service.context_retrieval", "service.recovery",
           "service.repair_demo", "service.repair_reporting", "evals", "compute", "workloads.registry"]
origins = {}
for name in modules:
    module = importlib.import_module(name)
    path = pathlib.Path(module.__file__).resolve()
    origins[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
distributions = {}
for dist in m.distributions():
    files = {}
    notices = {}
    for relative in dist.files or []:
        if str(relative).endswith((".pyc", ".pyo")):
            continue
        path = pathlib.Path(dist.locate_file(relative))
        if not path.is_file():
            raise RuntimeError("missing installed distribution file: " + str(relative))
        data = path.read_bytes()
        files[str(relative)] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if any(part.lower().startswith(("license", "copying", "notice")) for part in relative.parts):
            notices[str(relative)] = files[str(relative)]
    name = dist.metadata["Name"].lower().replace("_", "-")
    distributions[name] = {"version": dist.version, "files": files,
        "license_expression": dist.metadata.get("License-Expression"),
        "license": dist.metadata.get("License"), "notices": notices,
        "notice_completeness": "not independently reviewed"}
print(json.dumps({"python": platform.python_version(), "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                  "sys_path": sys.path, "origins": origins, "distributions": distributions}))
'''


def check_install_probe(probe: dict, manifest: dict, install_root: Path, forbidden: list[Path]) -> None:
    prefix = Path(probe["prefix"]).resolve()
    if prefix == Path(probe["base_prefix"]).resolve() or install_root.resolve() not in prefix.parents:
        raise ReleaseError("probe did not use the fresh isolated virtualenv")
    for name, item in probe["origins"].items():
        origin = Path(item["path"]).resolve()
        if prefix not in origin.parents or any(p.resolve() == origin or p.resolve() in origin.parents for p in forbidden):
            raise ReleaseError(f"installed import contamination: {name}")
        target = name.replace(".", "/") + ("/__init__.py" if origin.name == "__init__.py" else ".py")
        if item["sha256"] != manifest["files"][target]["sha256"]:
            raise ReleaseError(f"installed module bytes mismatch: {name}")
    for path in probe["sys_path"]:
        resolved = Path(path).resolve()
        if any(p.resolve() == resolved or p.resolve() in resolved.parents for p in forbidden):
            raise ReleaseError("forbidden checkout/test root in installed sys.path")
    project = probe["distributions"].get(manifest["project"]["name"])
    if not project or project["version"] != manifest["project"]["version"]:
        raise ReleaseError("installed product identity mismatch")
    for target, expected in manifest["files"].items():
        if runtime_asset(target) and project["files"].get(target) != {k: expected[k] for k in ("sha256", "size")}:
            raise ReleaseError(f"installed source/asset bytes mismatch: {target}")


def install(root: Path, candidate: Path, install_root: Path, uv: Path, cache: Path | None,
            wheelhouse: Path | None) -> dict:
    manifest = load_manifest(candidate / "frozen-manifest.json")
    check_sources(root, manifest)
    record = json.loads((candidate / "build-evidence.json").read_text(), object_pairs_hook=no_duplicates)
    wheels = list((candidate / "dist").glob("*.whl"))
    if len(wheels) != 1 or wheel_inventory(wheels[0], manifest) != record["wheel"]:
        raise ReleaseError("built wheel identity drift")
    if validate_archive(candidate / "source.tar.gz", manifest) != record["archive"]:
        raise ReleaseError("built source archive identity drift")
    requirements, expected_closure = export_requirements(root / "uv.lock", manifest["project"]["name"])
    closure = json.loads((candidate / "dependency-closure.json").read_text(), object_pairs_hook=no_duplicates)
    if closure != expected_closure or (candidate / "requirements-base.txt").read_text() != requirements:
        raise ReleaseError("locked requirement export drift")
    if (cache is None) == (wheelhouse is None):
        raise ReleaseError("choose exactly one local cache or wheelhouse")
    for forbidden in (root, candidate):
        if install_root.resolve() == forbidden.resolve() or forbidden.resolve() in install_root.resolve().parents:
            raise ReleaseError("installed work directory must be outside checkout and candidate")
    check_output(root, install_root, {})
    if (candidate / "install-evidence.json").exists() or (candidate / "install-failure.json").exists():
        raise ReleaseError("install evidence collision; use a fresh candidate for retry")
    material = {"route": "original-wheelhouse" if wheelhouse else "uv-cache",
                "original_wheel_hashes_verified": wheelhouse is not None,
                "cached_extracted_content_is_original_wheel": False}
    if wheelhouse:
        material.update(path=str(wheelhouse.absolute()), wheels=verify_wheelhouse(wheelhouse, closure))
    else:
        if not cache.is_dir():
            raise ReleaseError("missing explicit local uv cache")
        material.update(path=str(cache.absolute()), hash_policy="uv-require-hashes-cache-verification",
                        redistributed_wheelhouse=False)
    install_root.mkdir(parents=True)
    try:
        run([sys.executable, "-I", "-m", "venv", "--without-pip", str(install_root / "venv")],
            install_root, install_root / "venv-command.json")
        python = install_root / "venv/bin/python"
        combined = install_root / "requirements-install.txt"
        combined.write_text(requirements + f"{manifest['project']['name']} @ {wheels[0].absolute().as_uri()} "
                            f"--hash=sha256:{record['wheel']['sha256']}\n")
        command = [str(uv), "pip", "install", "--offline", "--no-deps", "--no-build", "--python", str(python),
                   "--require-hashes", "-r", str(combined)]
        if wheelhouse:
            command.extend(["--no-index", "--find-links", str(wheelhouse.absolute())])
        else:
            command.extend(["--cache-dir", str(cache.absolute())])
        uv_version = run([str(uv), "--version"], install_root, install_root / "uv-version.json").strip()
        run(command, install_root, install_root / "install-command.json")
        run([str(uv), "pip", "check", "--offline", "--python", str(python)], install_root,
            install_root / "dependency-check.json")
        probe = json.loads(run([str(python), "-I", "-c", PROBE], install_root, install_root / "probe-command.json"))
        check_install_probe(probe, manifest, install_root, [root, candidate])
        expected_versions = {name: p["version"] for name, p in closure["packages"].items()}
        expected_versions[manifest["project"]["name"]] = manifest["project"]["version"]
        if {name: p["version"] for name, p in probe["distributions"].items()} != expected_versions:
            raise ReleaseError("installed distribution set does not equal base lock closure plus product")
        check_sources(root, manifest)
        if wheel_inventory(wheels[0], manifest) != record["wheel"]:
            raise ReleaseError("wheel changed during installation")
        evidence = {"status": "installed", "install_root": str(install_root.absolute()), "python": str(python),
                    "manifest": identity(candidate / "frozen-manifest.json"), "wheel": identity(wheels[0]),
                    "requirements": identity(combined), "material": material, "probe": probe,
                    "uv": {"version": uv_version, "executable": str(uv), "binary": identity(uv.resolve())},
                    "source_before_after": "unchanged", "claims": {"network": False, "published": False,
                    "repair_context_acceptance": False, "dependency_licenses_independently_reviewed": False}}
        write_json(candidate / "install-evidence.json", evidence, exclusive=True)
        return evidence
    except Exception as exc:
        write_json(candidate / "install-failure.json", {"status": "failed", "error": str(exc),
                                                     "install_root": str(install_root)}, exclusive=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("--manifest", type=Path, required=True)
    built = commands.add_parser("build")
    built.add_argument("--manifest", type=Path, required=True)
    built.add_argument("--output", type=Path, required=True)
    installed = commands.add_parser("install")
    installed.add_argument("--candidate", type=Path, required=True)
    installed.add_argument("--install-root", type=Path, required=True)
    installed.add_argument("--uv", type=Path, required=True)
    material = installed.add_mutually_exclusive_group(required=True)
    material.add_argument("--cache", type=Path)
    material.add_argument("--wheelhouse", type=Path)
    checked = commands.add_parser("check-source")
    checked.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.absolute()
    try:
        if args.command == "freeze":
            result = freeze(root, args.manifest.absolute())
            print(json.dumps({"status": "frozen", "files": len(result["files"]),
                              "content_sha256": result["content_sha256"]}))
        elif args.command == "build":
            result = build(root, args.manifest.absolute(), args.output.absolute())
            print(json.dumps({"status": result["status"], "wheel": result["wheel"]["sha256"]}))
        elif args.command == "install":
            result = install(root, args.candidate.absolute(), args.install_root.absolute(), args.uv.absolute(),
                             args.cache, args.wheelhouse)
            print(json.dumps({"status": result["status"], "python": result["python"]}))
        else:
            check_sources(root, load_manifest(args.manifest))
            print(json.dumps({"status": "unchanged"}))
        return 0
    except (ReleaseError, OSError, ValueError, KeyError) as exc:
        print(f"release rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
