#!/usr/bin/env python3
"""Local immutable-skill data trace; no broker, provider, activation or execution authority."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import shutil

from service.artifacts import LocalArtifacts, digest_bytes
from service.skills import (SkillError, capture_skill_catalog, default_skills_config,
                            read_catalog_snapshot, read_skill_resource_snapshot)
import workloads


def run(output: Path) -> dict:
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(workloads.__file__).parent / "skills/verified-repair-guide"
    origin = output / "origin/verified-repair-guide"
    shutil.copytree(fixture, origin)
    artifacts = LocalArtifacts(output / "artifacts")
    tenant, task = "skills-demo", "capture"
    config = default_skills_config(
        {"origin_id": "authored-fixture", "scope": "fixture", "root_label": "verified-repair-guide"},
        "authored-v1", "capture-demo-v1",
    )
    capture = capture_skill_catalog([origin], artifacts, tenant, task, config)
    initial = read_catalog_snapshot(artifacts, tenant, task, capture, config)
    package = initial["packages"][0]
    resource = "references/checklist.md"
    original = package["resources"][resource]
    (origin / resource).write_bytes(b"BAD\nmutated origin after capture\n")
    after = read_catalog_snapshot(artifacts, tenant, task, capture, config)
    if after["packages"][0]["resources"][resource] != original:
        raise AssertionError("origin mutation altered the captured snapshot")
    offset, assembled, chunks = 0, bytearray(), []
    while offset < len(original):
        chunk = read_skill_resource_snapshot(artifacts, tenant, task, capture, config,
                                            package["package_digest"], resource, offset, 2)
        assembled.extend(base64.b64decode(chunk["data"], validate=True))
        chunks.append(chunk)
        offset = chunk["next_offset"]
    if bytes(assembled) != original:
        raise AssertionError("byte chunks failed to reconstruct the resource")
    eof = read_skill_resource_snapshot(artifacts, tenant, task, capture, config,
                                      package["package_digest"], resource, offset, 2)
    if eof["size"] != 0 or not eof["eof"]:
        raise AssertionError("exact EOF did not return an empty chunk")

    # Defect drill on a disposable copy; keep the original captured artifacts intact.
    damaged_root = output / "damaged-artifacts"
    shutil.copytree(output / "artifacts", damaged_root)
    damaged = LocalArtifacts(damaged_root)
    damaged._path(tenant, task, digest_bytes(original)).write_bytes(b"CORRUPTED\n")
    try:
        read_catalog_snapshot(damaged, tenant, task, capture, config)
    except SkillError as error:
        corruption = {"rejected": True, "code": error.code}
    else:
        raise AssertionError("damaged resource artifact was accepted")
    summary = {
        "schema": 1, "status": "passed", "evidence": "trusted_local_capture_only",
        "paid_execution": "disabled", "skills_activation": "not_implemented",
        "provider_requests": 0, "human_mastery": "not_assessed", "capture": capture,
        "config": config, "package_digest": package["package_digest"],
        "body_sha256": digest_bytes(package["body"]), "body_bytes": len(package["body"]),
        "resource_path": resource, "resource_sha256": digest_bytes(original),
        "resource_bytes": len(original), "origin_mutation_did_not_change_snapshot": True,
        "chunks": chunks, "exact_eof": eof, "separate_artifact_corruption": corruption,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (output / "catalog.json").write_text(json.dumps(initial["catalog"], indent=2, ensure_ascii=False) + "\n")
    (output / "package.json").write_text(json.dumps(package["manifest"], indent=2, ensure_ascii=False) + "\n")
    trace = f"""# Immutable capture: observed local trace

1. Capture the authored package into scoped artifacts; package `{package['package_digest']}`.
2. Catalog `{capture['catalog_digest']}` binds package identity and declared provenance.
3. Resource `{resource}` contains {len(original)} UTF-8 bytes, SHA-256 `{digest_bytes(original)}`.
4. Change only the origin resource to different bytes. Resolving the captured catalog still returns the original bytes.
5. Read exact two-byte chunks, including splits within multibyte UTF-8; concatenation reproduces the original hash. Read at exact EOF returns zero bytes.
6. Corrupt a separate copy of the resource artifact. Resolution refuses with `{corruption['code']}`. Original evidence remains intact.

No tool capability, successful-load receipt, model disclosure or recovery authority was created. Broker/provider integration is pending. This is AI-produced engineering evidence, not a prediction or mastery claim from Huy.

**VI:** Đổi source sau capture không đổi snapshot. Đổi bytes trong artifact lại phải bị phát hiện. Chunks là bytes nên có thể cắt giữa ký tự tiếng Việt; ghép đủ bytes rồi mới decode. Đây là kiểm dữ liệu, chưa phải activation của skill trong agent loop.
"""
    (output / "trace.md").write_text(trace)
    return {"status": summary["status"], "output": str(output),
            "summary_sha256": digest_bytes((output / "summary.json").read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output)))


if __name__ == "__main__":
    main()
