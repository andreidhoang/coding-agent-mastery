"""Immutable content-addressed bytes; a digest is identity, never authorization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def _read_cap(store_limit: int, requested: int | None) -> int:
    if requested is None:
        return store_limit
    if type(requested) is not int or requested <= 0:
        raise ValueError("artifact read limit must be a positive integer")
    return min(store_limit, requested)


def _scope(value: str) -> str:
    # contracts imports these digest helpers, so resolve its canonical namespace
    # validator lazily after module initialization instead of creating a cycle.
    from .contracts import identity

    return identity(value, "artifact scope")


class LocalArtifacts:
    """Trusted-control-plane storage only; candidate processes never receive this root."""

    def __init__(self, root: str | Path, max_bytes: int = 8 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.max_bytes = max_bytes

    def _path(self, tenant_id: str, task_id: str, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid sha256")
        path = self.root / _scope(tenant_id) / _scope(task_id) / digest
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("artifact path escaped root")
        return path

    def put(
        self, tenant_id: str, task_id: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> dict:
        if len(data) > self.max_bytes:
            raise ValueError("artifact exceeds configured byte limit")
        digest = digest_bytes(data)
        path = self._path(tenant_id, task_id, digest)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            if self.get(tenant_id, task_id, digest) != data:
                raise ValueError("content collision")
        else:
            fd, temporary = tempfile.mkstemp(dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Atomic no-overwrite publication: identical concurrent uploads converge.
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    self.get(tenant_id, task_id, digest)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                os.unlink(temporary)
        return {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "digest": digest,
            "size": len(data),
            "content_type": content_type,
        }

    def put_json(self, tenant_id: str, task_id: str, value: Any) -> dict:
        return self.put(tenant_id, task_id, canonical_bytes(value), "application/json")

    def get(self, tenant_id: str, task_id: str, digest: str, *, max_bytes: int | None = None) -> bytes:
        cap = _read_cap(self.max_bytes, max_bytes)
        path = self._path(tenant_id, task_id, digest)
        if path.is_symlink():
            raise ValueError("artifact symlink rejected")
        with path.open("rb") as stream:
            data = stream.read(cap + 1)
        if len(data) > cap or digest_bytes(data) != digest:
            raise ValueError("artifact integrity failure")
        return data

    def get_json(self, tenant_id: str, task_id: str, digest: str) -> Any:
        return json.loads(self.get(tenant_id, task_id, digest))


class S3Artifacts:
    """Optional S3 adapter; deployment must configure bucket versioning/retention/access policy."""

    def __init__(
        self, client: Any, bucket: str, prefix: str = "agent-evidence", max_bytes: int = 8 * 1024 * 1024
    ):
        self.client, self.bucket, self.prefix, self.max_bytes = client, bucket, prefix, max_bytes

    def _key(self, tenant_id: str, task_id: str, digest: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid sha256")
        return f"{self.prefix}/{_scope(tenant_id)}/{_scope(task_id)}/{digest}"

    def put(
        self, tenant_id: str, task_id: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> dict:
        if len(data) > self.max_bytes:
            raise ValueError("artifact exceeds configured byte limit")
        digest = digest_bytes(data)
        key = self._key(tenant_id, task_id, digest)
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, IfNoneMatch="*"
            )
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") not in {"PreconditionFailed", "412"}:
                raise
        if self.get(tenant_id, task_id, digest) != data:
            raise ValueError("S3 read-after-write integrity failure")
        return {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "digest": digest,
            "size": len(data),
            "content_type": content_type,
        }

    def get(self, tenant_id: str, task_id: str, digest: str, *, max_bytes: int | None = None) -> bytes:
        cap = _read_cap(self.max_bytes, max_bytes)
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(tenant_id, task_id, digest))
        body = response["Body"]
        try:
            data = body.read(cap + 1)
        finally:
            body.close()
        if len(data) > cap or digest_bytes(data) != digest:
            raise ValueError("S3 artifact integrity failure")
        return data

    def put_json(self, tenant_id: str, task_id: str, value: Any) -> dict:
        return self.put(tenant_id, task_id, canonical_bytes(value), "application/json")

    def get_json(self, tenant_id: str, task_id: str, digest: str) -> Any:
        return json.loads(self.get(tenant_id, task_id, digest))
