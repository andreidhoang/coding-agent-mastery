import asyncio

import httpx
import pytest

from service.api import Principal, create_app
from service.artifacts import LocalArtifacts
from service.storage import RuntimeStore


TOKEN_A = "explicit-test-token-for-tenant-a"
TOKEN_B = "explicit-test-token-for-tenant-b"
TOKEN_REVIEW = "explicit-reviewer-token-tenant-a"


@pytest.fixture
def api(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore(f"sqlite:///{tmp_path / 'runtime.sqlite'}", artifact_store=artifacts)
    app = create_app(
        store,
        tokens={
            TOKEN_A: Principal("tenant-a", "developer-a", frozenset({"repo-a"})),
            TOKEN_B: Principal("tenant-b", "developer-b", frozenset({"repo-b"})),
            TOKEN_REVIEW: Principal("tenant-a", "reviewer-a", frozenset({"repo-a"}), can_review=True),
        },
        artifact_store=artifacts,
    )
    yield app, store, artifacts
    store.close()


def request(app, method, path, token=TOKEN_A, **kwargs):
    async def call():
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://reference.test"
        ) as client:
            return await client.request(method, path, headers=headers, **kwargs)

    return asyncio.run(call())


def submit(app, *, key="submission", repo="repo-a", token=TOKEN_A):
    return request(
        app,
        "POST",
        "/tasks",
        token=token,
        json={
            "key": key,
            "contract": {"repo_id": repo, "base_revision": "frozen-base", "requirements": ["repair import"]},
        },
    )


def test_unconfigured_and_unauthenticated_api_fail_closed(api):
    app, store, _artifacts = api
    assert request(create_app(), "POST", "/tasks", token=None, json={}).status_code == 503
    assert request(app, "POST", "/tasks", token=None, json={}).status_code == 401
    assert request(app, "POST", "/tasks", token="wrong", json={}).status_code == 401
    assert store.list_outbox() == []
    with pytest.raises(ValueError):
        create_app(store, tokens={"default": Principal("tenant-a", "a", frozenset({"repo-a"}))})


def test_tenant_and_repository_authority_and_duplicate_submission(api):
    app, store, _artifacts = api
    first = submit(app)
    assert first.status_code == 202
    task = first.json()
    assert task["tenant_id"] == "tenant-a"
    assert submit(app).json()["task_id"] == task["task_id"]
    changed = request(
        app,
        "POST",
        "/tasks",
        json={
            "key": "submission",
            "contract": {"repo_id": "repo-a", "base_revision": "other", "requirements": ["repair"]},
        },
    )
    assert changed.status_code == 409
    forged = request(
        app, "POST", "/tasks", json={"tenant_id": "tenant-b", "key": "x", "contract": task["contract"]}
    )
    assert forged.status_code == 422
    assert submit(app, key="denied", repo="repo-b").status_code == 403
    research = request(
        app,
        "POST",
        "/tasks",
        json={
            "key": "research",
            "contract": {
                "repo_id": "repo-a",
                "base_revision": "base",
                "requirements": ["repair"],
                "profile": "research",
                "patch_slot_limit": 4,
            },
        },
    )
    assert research.status_code == 403
    assert request(app, "GET", f"/tasks/{task['task_id']}", token=TOKEN_B).status_code == 404
    assert (
        request(
            app, "POST", f"/tasks/{task['task_id']}/cancel", token=TOKEN_B, json={"request_id": "cancel"}
        ).status_code
        == 404
    )
    assert len(store.list_outbox()) == 1


def test_strict_bounded_ingress_duplicate_keys_and_nonfinite_values(api):
    app, store, _artifacts = api
    headers = {"Content-Type": "application/json"}
    for body in ('{"key":"a","key":"b","contract":{}}', '{"key":"a","contract":{"repo_id":NaN}}'):
        assert request(app, "POST", "/tasks", content=body, headers=headers).status_code == 400
    assert request(app, "POST", "/tasks", content="x" * 65537, headers=headers).status_code == 413
    assert (
        request(app, "POST", "/tasks", content="{}", headers={"Content-Type": "text/plain"}).status_code
        == 415
    )
    assert request(app, "POST", "/tasks", json={"key": "a", "contract": {"repo_id": []}}).status_code == 422
    assert store.list_outbox() == []


def test_chunked_request_body_is_bounded(api):
    app, store, _artifacts = api

    async def chunks():
        yield b"x" * 40000
        yield b"x" * 40000

    assert (
        request(
            app, "POST", "/tasks", content=chunks(), headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert store.list_outbox() == []


def test_sse_per_event_cursor_resumes_without_skipping_and_restore_resets(api):
    app, store, _artifacts = api
    task = submit(app).json()
    identifier = task["task_id"]
    store.cancel("tenant-a", identifier, "cancel-one")
    response = request(app, "GET", f"/tasks/{identifier}/events", headers={"Accept": "text/event-stream"})
    assert response.status_code == 200
    ids = [line.removeprefix("id: ") for line in response.text.splitlines() if line.startswith("id: ")]
    assert len(ids) >= 2
    assert len(set(ids)) == len(ids)
    resumed = request(app, "GET", f"/tasks/{identifier}/events", headers={"Last-Event-ID": ids[0]}).json()
    assert resumed["events"][0]["sequence"] == 2
    store.quarantine_restore("fresh-incarnation", {"backup_event": 1})
    reset = request(app, "GET", f"/tasks/{identifier}/events", headers={"Last-Event-ID": ids[0]})
    assert reset.status_code == 410
    assert reset.json()["error"]["code"] == "reset_required"
    assert reset.json()["error"]["snapshot"]["task"]["tenant_id"] == "tenant-a"
    assert (
        request(app, "GET", f"/tasks/{identifier}/events?limit=no").json()["error"]["code"]
        == "invalid_parameters"
    )


def test_artifact_membership_and_review_identity_and_no_verifier_route(api, monkeypatch):
    app, store, artifacts = api
    task = submit(app).json()
    identifier = task["task_id"]
    unbound = artifacts.put("tenant-a", identifier, b"unbound evidence")
    assert request(app, "GET", f"/tasks/{identifier}/artifacts/{unbound['digest']}").status_code == 404
    assert (
        request(
            app, "POST", f"/tasks/{identifier}/reviews/review-one", json={"decision": "accepted", "key": "r"}
        ).status_code
        == 403
    )
    observed = []
    monkeypatch.setattr(store, "record_review", lambda *args: observed.append(args) or {"reviewer": args[3]})
    review = request(
        app,
        "POST",
        f"/tasks/{identifier}/reviews/review-one",
        token=TOKEN_REVIEW,
        json={"decision": "accepted", "key": "r"},
    )
    assert review.status_code == 200
    assert observed[0][3] == "reviewer-a"
    forged = request(
        app,
        "POST",
        f"/tasks/{identifier}/reviews/review-one",
        token=TOKEN_REVIEW,
        json={"reviewer": "forged", "decision": "accepted", "key": "r"},
    )
    assert forged.status_code == 422
    assert len(observed) == 1
    assert (
        request(
            app, "POST", f"/tasks/{identifier}/verification", token=TOKEN_REVIEW, json={"passed": True}
        ).status_code
        == 404
    )
