"""Independent checks for the shared bounded artifact reader seam."""

import hashlib
import io
from pathlib import Path

import pytest

from service.artifacts import LocalArtifacts, S3Artifacts


class RecordingBody(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class S3ReadFixture:
    def __init__(self, data):
        self.data = data
        self.bodies = []
        self.requests = []

    def get_object(self, **request):
        self.requests.append(request)
        body = RecordingBody(self.data)
        self.bodies.append(body)
        return {"Body": body}


@pytest.mark.parametrize("backend", ["local", "s3"])
@pytest.mark.parametrize("cap,length,passes", [(3, 3, True), (3, 4, False), (9, 5, True), (9, 6, False)])
def test_shared_reader_effective_cap_and_cap_plus_one(tmp_path, monkeypatch, backend, cap, length, passes):
    data = b"x" * length
    digest = hashlib.sha256(data).hexdigest()
    effective = min(cap, 5)
    bodies = []
    if backend == "s3":
        client = S3ReadFixture(data)
        store = S3Artifacts(client, "test-bucket", max_bytes=5)
        bodies = client.bodies
    else:
        store = LocalArtifacts(tmp_path / "store", max_bytes=5)
        path = store.root / "tenant" / "task" / digest
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        original_open = Path.open

        def recording_open(path, *args, **kwargs):
            if path.name == digest:
                body = RecordingBody(data)
                bodies.append(body)
                return body
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", recording_open)
    if passes:
        assert store.get("tenant", "task", digest, max_bytes=cap) == data
    else:
        with pytest.raises(ValueError):
            store.get("tenant", "task", digest, max_bytes=cap)
    assert len(bodies) == 1
    assert bodies[0].read_sizes == [effective + 1]
    assert bodies[0].closed


@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.5, "3", {}, []])
@pytest.mark.parametrize("backend", ["local", "s3"])
def test_invalid_optional_cap_fails_before_open(tmp_path, monkeypatch, bad, backend):
    data = b"abc"
    digest = hashlib.sha256(data).hexdigest()
    if backend == "s3":
        client = S3ReadFixture(data)
        store = S3Artifacts(client, "test-bucket")
    else:
        store = LocalArtifacts(tmp_path / "store")
        def forbidden_open(*args, **kwargs):
            pytest.fail("invalid cap reached filesystem open")
        monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(ValueError):
        store.get("tenant", "task", digest, max_bytes=bad)
    if backend == "s3":
        assert not client.requests


@pytest.mark.parametrize("backend", ["local", "s3"])
def test_omitted_cap_retains_legacy_read_limit(tmp_path, monkeypatch, backend):
    data = b"legacy"
    digest = hashlib.sha256(data).hexdigest()
    if backend == "s3":
        client = S3ReadFixture(data)
        store = S3Artifacts(client, "test-bucket", max_bytes=7)
        assert store.get("tenant", "task", digest) == data
        assert client.bodies[0].read_sizes == [8]
    else:
        store = LocalArtifacts(tmp_path / "store", max_bytes=7)
        store.put("tenant", "task", data)
        body = RecordingBody(data)
        monkeypatch.setattr(Path, "open", lambda *a, **k: body)
        assert store.get("tenant", "task", digest) == data
        assert body.read_sizes == [8]


@pytest.mark.parametrize("backend", ["local", "s3"])
def test_bounded_reader_still_checks_content_hash(tmp_path, backend):
    data = b"abc"
    digest = hashlib.sha256(b"abd").hexdigest()
    if backend == "s3":
        store = S3Artifacts(S3ReadFixture(data), "test-bucket")
    else:
        store = LocalArtifacts(tmp_path / "store")
        path = store.root / "tenant" / "task" / digest
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
    with pytest.raises(ValueError):
        store.get("tenant", "task", digest, max_bytes=3)
