import base64

import pytest

from service.artifacts import LocalArtifacts
from service.context_retrieval import read_context_artifact


def setup(tmp_path):
    artifacts = LocalArtifacts(tmp_path)
    data = "xin chào 🌏".encode()
    ref = artifacts.put("t", "x", data)
    entry = {"call_id": "c", "message_index": 1, "block_index": None, "digest": ref["digest"],
             "size": len(data), "encoding": "utf-8", "artifact_ref": ref}
    return artifacts, data, entry


def test_exact_byte_chunks_and_eof(tmp_path):
    artifacts, data, entry = setup(tmp_path)
    output = b""
    offset = 0
    while offset < len(data):
        chunk = read_context_artifact(artifacts, "t", "x", [entry],
                                      {"digest": entry["digest"], "offset": offset, "limit": 1})
        output += base64.b64decode(chunk["bytes_base64"])
        offset = chunk["next_offset"]
    assert output == data and chunk["eof"]


@pytest.mark.parametrize("offset,limit", [(True, 1), (0, True), (-1, 1), (0, 0), (0, 8193), (999, 1)])
def test_bad_ranges(tmp_path, offset, limit):
    artifacts, _, entry = setup(tmp_path)
    with pytest.raises(ValueError):
        read_context_artifact(artifacts, "t", "x", [entry],
                              {"digest": entry["digest"], "offset": offset, "limit": limit})


def test_denies_unrelated_foreign_tampered_and_paths(tmp_path):
    artifacts, _, entry = setup(tmp_path)
    args = {"digest": entry["digest"], "offset": 0, "limit": 1}
    with pytest.raises(PermissionError):
        read_context_artifact(artifacts, "t", "x", [], args)
    with pytest.raises(ValueError):
        read_context_artifact(artifacts, "t", "other", [entry], args)
    with pytest.raises(ValueError):
        read_context_artifact(artifacts, "t", "x", [entry], {**args, "path": "/etc/passwd"})
    artifacts._path("t", "x", entry["digest"]).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        read_context_artifact(artifacts, "t", "x", [entry], args)


def test_reference_boolean_size_cannot_alias_integer(tmp_path):
    artifacts, _, entry = setup(tmp_path)
    ref = artifacts.put("t", "x", b"x")
    entry.update(digest=ref["digest"], size=1, artifact_ref={**ref, "size": True})
    with pytest.raises(ValueError):
        read_context_artifact(artifacts, "t", "x", [entry],
                              {"digest": ref["digest"], "offset": 0, "limit": 1})
