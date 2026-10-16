"""Bounded ASGI memory and consistent authority/artifact namespace regressions."""

import asyncio
import tracemalloc

import httpx
import pytest

from service.api import BoundedIngress, Principal, create_app
from service.artifacts import LocalArtifacts, S3Artifacts
from service.contracts import identity
from service.engine import ReferenceEngine
from service.storage import RuntimeStore
from workloads import list_tasks


def test_empty_asgi_chunks_use_one_bounded_body_replay():
    async def exercise():
        received = []
        chunk = 0

        async def receive():
            nonlocal chunk
            chunk += 1
            if chunk <= 30000:
                return {"type": "http.request", "body": b"", "more_body": True}
            if chunk == 30001:
                return {"type": "http.request", "body": b"{}", "more_body": False}
            return {"type": "http.disconnect"}

        async def downstream(scope, receive, send):
            received.append(await receive())
            received.append(await receive())

        async def send(message):
            raise AssertionError("valid bounded stream must reach app")

        tracemalloc.start()
        try:
            await BoundedIngress(downstream, 1024)({"type": "http", "headers": []}, receive, send)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert received == [
            {"type": "http.request", "body": b"{}", "more_body": False},
            {"type": "http.disconnect"},
        ]
        assert peak < 200000, peak  # Original message list retained over 5 MB.

    asyncio.run(exercise())


def test_colon_tenant_api_submission_completes_fixture_and_saves_evidence(tmp_path):
    token = "colon-namespace-explicit-token"
    tenant = "tenant:blue"
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "authority.sqlite"), artifacts)
    engine = ReferenceEngine(store, artifacts, tmp_path / "workers")
    task = engine.submit_fixture(list_tasks(split="calibration")[0].task_id, tenant=tenant, key="prepare")
    contract = task["contract"]
    app = create_app(
        store,
        tokens={token: Principal(tenant, "developer:one", frozenset({contract["repo_id"]}))},
        artifact_store=artifacts,
    )

    async def submit():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture.test"
        ) as client:
            return await client.post(
                "/tasks",
                headers={"Authorization": "Bearer " + token},
                json={"key": "api:submission", "contract": contract},
            )

    try:
        response = asyncio.run(submit())
        assert response.status_code == 202, response.text
        submitted = response.json()
        snapshot = engine.run_task(tenant, submitted["task_id"])
        assert snapshot["task"]["execution_state"] == "review_eligible"
        assert snapshot["dispatches"] and snapshot["checkpoints"]
        for dispatch in snapshot["dispatches"]:
            if dispatch.get("result_ref"):
                assert artifacts.get(tenant, submitted["task_id"], dispatch["result_ref"]["digest"])
        assert snapshot["budget"]["reserved"] == 0
    finally:
        store.close()


@pytest.mark.parametrize("namespace", ["tenant:blue", "tenant", "tenant_1.2-3", "a:b:c"])
def test_artifact_namespace_matches_authority_identity(tmp_path, namespace):
    identity(namespace)
    artifacts = LocalArtifacts(tmp_path)
    ref = artifacts.put(namespace, "task:one", b"evidence")
    assert artifacts.get(namespace, "task:one", ref["digest"]) == b"evidence"
    # Both adapters derive the same safe scope; this does not call a cloud API.
    key = S3Artifacts(None, "unused")._key(namespace, "task:one", ref["digest"])
    assert key.endswith(namespace + "/task:one/" + ref["digest"])


@pytest.mark.parametrize(
    "namespace", ["../escape", "tenant/blue", "tenant\\blue", "tenant\x00blue", ":tenant"]
)
def test_escaping_artifact_namespaces_remain_invalid(tmp_path, namespace):
    with pytest.raises(ValueError):
        LocalArtifacts(tmp_path).put(namespace, "task", b"bad")
