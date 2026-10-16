"""Immutable, bounded skill data capture. These helpers grant no execution authority."""
from __future__ import annotations

import base64
import json
import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path

import yaml
from yaml.events import (AliasEvent, DocumentStartEvent, MappingEndEvent, MappingStartEvent,
                         ScalarEvent, SequenceStartEvent)
from yaml.tokens import DirectiveToken

from .artifacts import canonical_bytes, digest_bytes, digest_json
from .contracts import identity, parse_json

PROFILE = "immutable_text_skill_v1"
LIMITS = {
    "max_packages": 1, "max_loaded_packages": 1, "max_skill_bytes": 65536,
    "max_frontmatter_bytes": 8192, "max_body_bytes": 32768,
    "max_catalog_bytes": 16384, "max_manifest_bytes": 65536,
    "max_resources": 64, "max_directories": 64, "max_path_depth": 4,
    "max_resource_bytes": 262144, "max_total_resource_bytes": 4194304,
    "max_path_bytes": 240, "max_component_bytes": 64, "max_yaml_depth": 8,
    "max_yaml_nodes": 256, "max_metadata_entries": 32,
    "max_metadata_scalar_bytes": 1024, "max_read_bytes": 8192, "max_result_bytes": 65536,
}
_REF_KEYS = {"tenant_id", "task_id", "digest", "size", "content_type"}
_CAPTURE_KEYS = {"config_ref", "config_digest", "catalog_ref", "catalog_digest"}
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9._-]+\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class SkillError(ValueError):
    """Stable bounded rejection; messages deliberately contain no source inputs."""
    def __init__(self, code="invalid_package"):
        self.code = code
        super().__init__(code)


def _fail(code="invalid_package"):
    raise SkillError(code) from None


def _closed(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail()


def _schema(value):
    if type(value) is not int or value != 1:
        _fail("unsupported_profile")


def _hash(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail()


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail("bounds_exceeded")


def _copy(value):
    return json.loads(canonical_bytes(value))


def _text(value, cap, *, ascii_only=False):
    if not isinstance(value, str) or not value:
        _fail()
    if len(value) > cap:
        _fail("bounds_exceeded")
    try:
        raw = value.encode("ascii" if ascii_only else "utf-8")
    except UnicodeError:
        _fail()
    if len(raw) > cap:
        _fail("bounds_exceeded")


def _origin(value):
    _closed(value, {"origin_id", "scope", "root_label"})
    if value["scope"] != "fixture":
        _fail("unsupported_profile")
    for key in ("origin_id", "root_label"):
        _text(value[key], 128, ascii_only=True)


def default_skills_config(origin, source_revision, catalog_revision):
    return validate_skills_config({"schema": 1, "profile": PROFILE, "limits": dict(LIMITS),
                                   "origin": origin, "source_revision": source_revision,
                                   "catalog_revision": catalog_revision})


def validate_skills_config(config):
    _closed(config, {"schema", "profile", "limits", "origin", "source_revision", "catalog_revision"})
    _schema(config["schema"])
    if config["profile"] != PROFILE:
        _fail("unsupported_profile")
    _closed(config["limits"], LIMITS)
    for key, expected in LIMITS.items():
        if type(config["limits"][key]) is not int or config["limits"][key] != expected:
            _fail("bounds_exceeded")
    _origin(config["origin"])
    for key in ("source_revision", "catalog_revision"):
        _text(config[key], 128)
    return _copy(config)


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or not _NAME.fullmatch(value):
        _fail()


def _path(value):
    if not isinstance(value, str):
        _fail("resource_denied")
    if len(value) > LIMITS["max_path_bytes"]:
        _fail("bounds_exceeded")
    try:
        raw = value.encode("ascii")
    except UnicodeError:
        _fail("resource_denied")
    parts = value.split("/")
    if len(raw) > LIMITS["max_path_bytes"] or len(parts) > LIMITS["max_path_depth"]:
        _fail("bounds_exceeded")
    if any(not p or p.startswith(".") or len(p) > LIMITS["max_component_bytes"]
           or not _COMPONENT.fullmatch(p) for p in parts):
        _fail("resource_denied")
    return parts


def _utf8(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        _fail()


def _metadata(value, package_name):
    if not isinstance(value, dict) or not {"name", "description"} <= set(value):
        _fail()
    if set(value) - {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}:
        _fail()
    _name(value["name"])
    if value["name"] != package_name:
        _fail()
    for key, item in value.items():
        if key == "metadata":
            if not isinstance(item, dict):
                _fail()
            if len(item) > LIMITS["max_metadata_entries"]:
                _fail("bounds_exceeded")
            for k, v in item.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    _fail()
                if max(len(k.encode("utf-8")), len(v.encode("utf-8"))) > 1024:
                    _fail("bounds_exceeded")
        elif not isinstance(item, str):
            _fail()
    description = value["description"]
    if not description.strip() or not 1 <= len(description) <= 1024:
        _fail("bounds_exceeded")
    if "compatibility" in value and not 1 <= len(value["compatibility"]) <= 500:
        _fail("bounds_exceeded")
    return _copy(value)


def _yaml_mapping(text):
    # Tokens catch even unknown directives that the parser would otherwise ignore.
    try:
        for token in yaml.scan(text, Loader=yaml.BaseLoader):
            if isinstance(token, DirectiveToken):
                _fail()
        events = []
        nodes = depth = documents = 0
        for event in yaml.parse(text, Loader=yaml.BaseLoader):
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1 or event.version or event.tags:
                    _fail()
            if isinstance(event, (AliasEvent, SequenceStartEvent)):
                _fail()
            if getattr(event, "anchor", None) or getattr(event, "tag", None):
                _fail()
            if isinstance(event, (ScalarEvent, MappingStartEvent)):
                nodes += 1
                if nodes > LIMITS["max_yaml_nodes"]:
                    _fail("bounds_exceeded")
            if isinstance(event, MappingStartEvent):
                depth += 1
                if depth > LIMITS["max_yaml_depth"]:
                    _fail("bounds_exceeded")
            elif isinstance(event, MappingEndEvent):
                depth -= 1
            events.append(event)
    except SkillError:
        raise
    except yaml.YAMLError:
        _fail()
    # Construction occurs only after every event has passed bounded validation.
    nodes = [e for e in events if isinstance(e, (ScalarEvent, MappingStartEvent, MappingEndEvent))]
    index = 0

    def consume():
        nonlocal index
        if index >= len(nodes):
            _fail()
        event = nodes[index]
        index += 1
        if isinstance(event, ScalarEvent):
            return event.value
        if not isinstance(event, MappingStartEvent):
            _fail()
        result = {}
        while index < len(nodes) and not isinstance(nodes[index], MappingEndEvent):
            key = consume()
            if not isinstance(key, str) or key == "<<" or key in result:
                _fail()
            result[key] = consume()
        if index >= len(nodes):
            _fail()
        index += 1
        return result

    result = consume()
    if index != len(nodes) or not isinstance(result, dict):
        _fail()
    return result


def parse_skill_file(raw, package_name, config):
    validate_skills_config(config)
    _name(package_name)
    if not isinstance(raw, bytes):
        _fail()
    if len(raw) > LIMITS["max_skill_bytes"]:
        _fail("bounds_exceeded")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw or b"\r" in raw or not raw.startswith(b"---\n"):
        _fail()
    _utf8(raw)
    end = 4
    while end < len(raw):
        newline = raw.find(b"\n", end)
        if newline == -1:
            _fail()
        if raw[end:newline + 1] == b"---\n":
            break
        end = newline + 1
    else:
        _fail()
    frontmatter = raw[4:end]
    body = raw[newline + 1:]
    if len(frontmatter) > LIMITS["max_frontmatter_bytes"] or len(body) > LIMITS["max_body_bytes"]:
        _fail("bounds_exceeded")
    try:
        return _metadata(_yaml_mapping(_utf8(frontmatter)), package_name), body
    except UnicodeError:
        _fail()


def _stat_key(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _descriptor_support():
    if (not all(hasattr(os, k) for k in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
            or os.scandir not in os.supports_fd):
        _fail("unsupported_profile")


def _open_root(root):
    _descriptor_support()
    # abspath is lexical, so a symlink ancestor cannot disappear through resolve().
    absolute = os.path.abspath(os.fspath(root))
    parts = Path(absolute).parts[1:]
    descriptor = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in parts:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _capture_source(root):
    fd = _open_root(root)
    try:
        device = os.fstat(fd).st_dev
        counts = {"resources": 0, "directories": 0, "bytes": 0}
        inventory, files, observed = {}, {}, set()

        def walk(directory, prefix, retain):
            initial = _stat_key(os.fstat(directory))
            local_names, entries = set(), []
            # Never materialize an unbounded directory listing.
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    relative = prefix + entry.name
                    parts = _path(relative)
                    folded = entry.name.casefold()
                    if folded in local_names:
                        _fail()
                    local_names.add(folded)
                    if len(entries) >= LIMITS["max_resources"] + LIMITS["max_directories"] + 1:
                        _fail("bounds_exceeded")
                    info = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                    if info.st_dev != device or stat.S_ISLNK(info.st_mode):
                        _fail()
                    if not prefix:
                        if entry.name == "SKILL.md":
                            if not stat.S_ISREG(info.st_mode):
                                _fail()
                        elif entry.name not in {"references", "assets"} or not stat.S_ISDIR(info.st_mode):
                            _fail()
                    elif parts[0] not in {"references", "assets"}:
                        _fail()
                    entries.append((entry.name, relative, info))
            for name, relative, info in sorted(entries):
                key = _stat_key(info)
                if retain:
                    inventory[relative] = key
                elif inventory.get(relative) != key:
                    _fail()
                if not retain:
                    observed.add(relative)
                if stat.S_ISDIR(info.st_mode):
                    if retain:
                        counts["directories"] += 1
                        if counts["directories"] > LIMITS["max_directories"]:
                            _fail("bounds_exceeded")
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        if _stat_key(os.fstat(child)) != key:
                            _fail()
                        walk(child, relative + "/", retain)
                    finally:
                        os.close(child)
                else:
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                    try:
                        before = os.fstat(file_fd)
                        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or _stat_key(before) != key:
                            _fail()
                        cap = LIMITS["max_skill_bytes"] if relative == "SKILL.md" else LIMITS["max_resource_bytes"]
                        if before.st_size > cap:
                            _fail("bounds_exceeded")
                        if retain:
                            if relative != "SKILL.md":
                                counts["resources"] += 1
                                counts["bytes"] += before.st_size
                                if counts["resources"] > 64 or counts["bytes"] > LIMITS["max_total_resource_bytes"]:
                                    _fail("bounds_exceeded")
                            chunks, remaining = [], cap + 1
                            while remaining:
                                chunk = os.read(file_fd, remaining)
                                if not chunk:
                                    break
                                chunks.append(chunk)
                                remaining -= len(chunk)
                            raw = b"".join(chunks)
                            if len(raw) > cap:
                                _fail("bounds_exceeded")
                            if len(raw) != before.st_size:
                                _fail()
                            _utf8(raw)
                            files[relative] = raw
                        if _stat_key(os.fstat(file_fd)) != key:
                            _fail()
                    finally:
                        os.close(file_fd)
            if _stat_key(os.fstat(directory)) != initial:
                _fail()
            return {relative for _, relative, _ in entries}

        walk(fd, "", True)
        # A second complete bounded walk detects changed/deleted/added inventory.
        walk(fd, "", False)
        if observed != set(inventory):
            _fail()
        if "SKILL.md" not in files:
            _fail()
        return files
    finally:
        os.close(fd)


def _ref(ref, tenant, task, cap, content_type):
    _closed(ref, _REF_KEYS)
    if ref["tenant_id"] != tenant or ref["task_id"] != task or ref["content_type"] != content_type:
        _fail()
    _hash(ref["digest"])
    _integer(ref["size"], 0, cap)


def _read_ref(artifacts, tenant, task, ref, cap, content_type):
    _ref(ref, tenant, task, cap, content_type)
    try:
        raw = artifacts.get(tenant, task, ref["digest"], max_bytes=max(1, cap))
    except Exception:
        _fail()
    if len(raw) != ref["size"] or digest_bytes(raw) != ref["digest"]:
        _fail()
    return raw


def _put(artifacts, tenant, task, raw, content_type, cap):
    if len(raw) > cap:
        _fail("bounds_exceeded")
    ref = artifacts.put(tenant, task, raw, content_type)
    if _read_ref(artifacts, tenant, task, ref, cap, content_type) != raw:
        _fail()
    return ref


def _read_json(artifacts, tenant, task, ref, cap):
    raw = _read_ref(artifacts, tenant, task, ref, cap, "application/json")
    try:
        value = parse_json(raw)
        if canonical_bytes(value) != raw:
            _fail()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def capture_skill_catalog(package_roots, artifacts, tenant_id, task_id, config):
    config = validate_skills_config(config)
    try:
        identity(tenant_id)
        identity(task_id)
        if not isinstance(package_roots, Sequence) or isinstance(package_roots, (str, bytes)):
            _fail()
        if len(package_roots) != 1:
            _fail("bounds_exceeded")
        root = package_roots[0]
        name = Path(os.path.abspath(os.fspath(root))).name
        _name(name)
        files = _capture_source(root)
        full = files.pop("SKILL.md")
        metadata, body = parse_skill_file(full, name, config)
        return _publish_catalog(artifacts, tenant_id, task_id, config, name, metadata, body, full, files)
    except SkillError:
        raise
    except Exception:
        _fail()


def _publish_catalog(artifacts, tenant, task, config, name, metadata, body, full, files):
    skill_ref = _put(artifacts, tenant, task, full, "text/markdown", LIMITS["max_skill_bytes"])
    body_ref = _put(artifacts, tenant, task, body, "text/markdown", LIMITS["max_body_bytes"])
    resources = [{"path": path, "artifact_ref": _put(artifacts, tenant, task, raw, "text/plain",
                  LIMITS["max_resource_bytes"]), "encoding": "utf-8"} for path, raw in sorted(files.items())]
    manifest = {"schema": 1, "profile": PROFILE, "origin": config["origin"],
                "source_revision": config["source_revision"], "name": name, "metadata": metadata,
                "skill_ref": skill_ref, "body_ref": body_ref, "resources": resources}
    package_ref = _put(artifacts, tenant, task, canonical_bytes(manifest), "application/json",
                       LIMITS["max_manifest_bytes"])
    catalog = {"schema": 1, "profile": PROFILE, "tenant_id": tenant, "task_id": task,
               "config_digest": digest_json(config), "catalog_revision": config["catalog_revision"],
               "entries": [{"name": name, "description": metadata["description"], "origin": config["origin"],
                            "source_revision": config["source_revision"],
                            "package_digest": package_ref["digest"], "package_ref": package_ref}]}
    config_ref = _put(artifacts, tenant, task, canonical_bytes(config), "application/json",
                      LIMITS["max_manifest_bytes"])
    catalog_ref = _put(artifacts, tenant, task, canonical_bytes(catalog), "application/json",
                       LIMITS["max_catalog_bytes"])
    return {"config_ref": config_ref, "config_digest": config_ref["digest"],
            "catalog_ref": catalog_ref, "catalog_digest": catalog_ref["digest"]}


def read_catalog_snapshot(artifacts, tenant_id, task_id, capture, config):
    config = validate_skills_config(config)
    try:
        identity(tenant_id)
        identity(task_id)
        _closed(capture, _CAPTURE_KEYS)
        for key in ("config_digest", "catalog_digest"):
            _hash(capture[key])
            if capture[key] != capture[key.removesuffix("digest") + "ref"]["digest"]:
                _fail("stale_catalog")
        stored_config = _read_json(artifacts, tenant_id, task_id, capture["config_ref"], LIMITS["max_manifest_bytes"])
        if validate_skills_config(stored_config) != config or digest_json(config) != capture["config_digest"]:
            _fail("stale_catalog")
        catalog = _read_json(artifacts, tenant_id, task_id, capture["catalog_ref"], LIMITS["max_catalog_bytes"])
        _closed(catalog, {"schema", "profile", "tenant_id", "task_id", "config_digest", "catalog_revision", "entries"})
        _schema(catalog["schema"])
        if (catalog["profile"] != PROFILE or catalog["tenant_id"] != tenant_id
                or catalog["task_id"] != task_id or catalog["config_digest"] != capture["config_digest"]
                or catalog["catalog_revision"] != config["catalog_revision"]):
            _fail("stale_catalog")
        entries = catalog["entries"]
        if not isinstance(entries, list) or len(entries) != 1:
            _fail()
        entry = entries[0]
        _closed(entry, {"name", "description", "origin", "source_revision", "package_digest", "package_ref"})
        _name(entry["name"])
        _hash(entry["package_digest"])
        if (entry["origin"] != config["origin"] or entry["source_revision"] != config["source_revision"]
                or entry["package_digest"] != entry["package_ref"]["digest"]):
            _fail()
        manifest = _read_json(artifacts, tenant_id, task_id, entry["package_ref"], LIMITS["max_manifest_bytes"])
        _closed(manifest, {"schema", "profile", "origin", "source_revision", "name", "metadata",
                           "skill_ref", "body_ref", "resources"})
        _schema(manifest["schema"])
        if (manifest["profile"] != PROFILE or manifest["origin"] != config["origin"]
                or manifest["source_revision"] != config["source_revision"] or manifest["name"] != entry["name"]):
            _fail()
        full = _read_ref(artifacts, tenant_id, task_id, manifest["skill_ref"], LIMITS["max_skill_bytes"], "text/markdown")
        metadata, body = parse_skill_file(full, entry["name"], config)
        stored_body = _read_ref(artifacts, tenant_id, task_id, manifest["body_ref"], LIMITS["max_body_bytes"], "text/markdown")
        if metadata != manifest["metadata"] or entry["description"] != metadata["description"] or body != stored_body:
            _fail()
        descriptors = manifest["resources"]
        if not isinstance(descriptors, list) or len(descriptors) > LIMITS["max_resources"]:
            _fail("bounds_exceeded")
        paths, folded, directories, resources, total = [], {}, set(), {}, 0
        for descriptor in descriptors:
            _closed(descriptor, {"path", "artifact_ref", "encoding"})
            path = descriptor["path"]
            parts = _path(path)
            if len(parts) < 2 or parts[0] not in {"references", "assets"} or descriptor["encoding"] != "utf-8":
                _fail()
            if path in resources:
                _fail()
            for index in range(1, len(parts) + 1):
                component_path = "/".join(parts[:index])
                prior = folded.setdefault(component_path.casefold(), component_path)
                if prior != component_path:
                    _fail()
            paths.append(path)
            directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
            if len(directories) > LIMITS["max_directories"]:
                _fail("bounds_exceeded")
            _ref(descriptor["artifact_ref"], tenant_id, task_id, LIMITS["max_resource_bytes"], "text/plain")
            total += descriptor["artifact_ref"]["size"]
            if total > LIMITS["max_total_resource_bytes"]:
                _fail("bounds_exceeded")
            raw = _read_ref(artifacts, tenant_id, task_id, descriptor["artifact_ref"], LIMITS["max_resource_bytes"], "text/plain")
            _utf8(raw)
            resources[path] = raw
        if paths != sorted(paths):
            _fail()
        if set(paths) & directories:
            _fail()
        return {"config": _copy(config), "catalog": catalog,
                "packages": [{"manifest": manifest, "package_digest": entry["package_digest"],
                              "body": body, "resources": resources}]}
    except SkillError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        _fail()


def read_skill_resource_snapshot(artifacts, tenant_id, task_id, capture, config,
                                 package_digest, path, offset, limit):
    _hash(package_digest)
    _path(path)
    _integer(limit, 1, LIMITS["max_read_bytes"])
    _integer(offset, 0, LIMITS["max_resource_bytes"])
    snapshot = read_catalog_snapshot(artifacts, tenant_id, task_id, capture, config)
    package = snapshot["packages"][0]
    if package["package_digest"] != package_digest or path not in package["resources"]:
        _fail("resource_denied")
    raw = package["resources"][path]
    _integer(offset, 0, len(raw))
    chunk = raw[offset:offset + limit]
    value = {"catalog_digest": capture["catalog_digest"], "package_digest": package_digest,
             "path": path, "digest": digest_bytes(raw), "offset": offset, "total_size": len(raw),
             "size": len(chunk), "next_offset": offset + len(chunk), "eof": offset + len(chunk) == len(raw),
             "encoding": "base64", "data": base64.b64encode(chunk).decode("ascii")}
    if len(canonical_bytes(value)) > LIMITS["max_result_bytes"]:
        _fail("bounds_exceeded")
    return value
