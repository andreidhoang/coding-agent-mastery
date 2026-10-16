"""Authenticated bounded HTTP surface; domain authority stays in RuntimeStore.

No verifier/operator routes exist. Bearer tokens must be explicitly configured
by trusted application startup; caller JSON never selects a tenant or reviewer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .contracts import (
    BudgetExceeded,
    CapacityExceeded,
    NotFound,
    ResetRequired,
    RuntimeErrorBase,
    Unsupported,
    digest,
    identity,
    parse_json,
    strict_int,
)


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject_id: str
    repositories: frozenset[str]
    can_review: bool = False
    profiles: frozenset[str] = frozenset({"production"})

    def __post_init__(self):
        identity(self.tenant_id, "tenant_id")
        identity(self.subject_id, "subject_id")
        if not isinstance(self.repositories, frozenset) or any(
            not isinstance(value, str) or not value or len(value) > 512 for value in self.repositories
        ):
            raise ValueError("repository grants must be an immutable bounded set")
        if type(self.can_review) is not bool:
            raise ValueError("review permission must be boolean")
        if (
            not isinstance(self.profiles, frozenset)
            or not self.profiles
            or not self.profiles <= {"production", "research"}
        ):
            raise ValueError("configure an immutable set of allowed execution profiles")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message[:500], **extra}}, status_code=status)


class BoundedIngress:
    """Bound HTTP request bodies before routing, including chunked requests."""

    def __init__(self, app, max_body_bytes: int):
        self.app, self.max_body_bytes = app, max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        if lengths:
            try:
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError("ambiguous length")
                length = int(lengths[0])
            except ValueError:
                await _error(400, "invalid_body_length", "invalid Content-Length")(scope, receive, send)
                return
            if length > self.max_body_bytes:
                await _error(413, "payload_too_large", "request body exceeds configured limit")(
                    scope, receive, send
                )
                return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                await _error(400, "invalid_body", "invalid request stream")(scope, receive, send)
                return
            chunk = message.get("body", b"")
            if not isinstance(chunk, bytes):
                await _error(400, "invalid_body", "request chunks must be bytes")(scope, receive, send)
                return
            if len(body) + len(chunk) > self.max_body_bytes:
                await _error(413, "payload_too_large", "request body exceeds configured limit")(
                    scope, receive, send
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        coalesced = bytes(body)
        del body
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": coalesced, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _body(request: Request, required: set[str], optional: set[str] = frozenset()) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise APIError(415, "unsupported_content_type", "application/json is required")
    try:
        body = parse_json(await request.body())
    except (ValueError, UnicodeError, RecursionError) as error:
        raise APIError(400, "invalid_json", "JSON must have unique keys and finite values") from error
    if not isinstance(body, dict) or set(body) - required - optional or required - set(body):
        raise APIError(422, "invalid_body", "request object has missing or unknown fields")
    return body


def create_app(
    store=None,
    *,
    tokens: Mapping[str, Principal] | None = None,
    artifact_store=None,
    max_body_bytes: int = 65536,
    contract_admission=None,
    contract_catalog=None,
    readiness=None,
    lifespan=None,
) -> FastAPI:
    """Unconfigured startup is fail-closed. No default credential is created."""
    strict_int(max_body_bytes, "max_body_bytes", 1024, 1048576)
    principals = {}
    for token, principal in (tokens or {}).items():
        if not isinstance(token, str) or not 24 <= len(token) <= 512 or not isinstance(principal, Principal):
            raise ValueError(
                "configure explicit bearer tokens of 24..512 characters and validated principals"
            )
        principals[hashlib.sha256(token.encode()).digest()] = principal
    configured = store is not None and bool(principals)
    app = FastAPI(title="Bounded coding-agent reference", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(BoundedIngress, max_body_bytes=max_body_bytes)

    @app.exception_handler(APIError)
    async def api_error(_request, error):
        response = _error(error.status, error.code, error.message)
        if error.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(RuntimeErrorBase)
    async def domain_error(_request, error):
        if isinstance(error, ResetRequired):
            return _error(
                410,
                "reset_required",
                "event cursor requires a fresh authorized snapshot",
                snapshot=error.snapshot,
            )
        status = (
            404
            if isinstance(error, NotFound)
            else 429
            if isinstance(error, CapacityExceeded)
            else 403
            if isinstance(error, BudgetExceeded)
            else 503
            if isinstance(error, Unsupported)
            else 409
        )
        message = "resource not found" if isinstance(error, NotFound) else str(error)
        return _error(status, type(error).__name__, message)

    @app.exception_handler(ValueError)
    async def invalid_value(_request, error):
        return _error(422, "invalid_input", str(error))

    @app.exception_handler(RequestValidationError)
    async def invalid_parameters(_request, _error_value):
        return _error(422, "invalid_parameters", "path or query parameter is invalid")

    def authenticate(request: Request) -> Principal:
        if not configured:
            raise APIError(
                503, "api_unconfigured", "API requires a configured authority store and bearer principals"
            )
        headers = request.headers.getlist("authorization")
        if len(headers) != 1 or len(headers[0]) > 520:
            raise APIError(401, "unauthenticated", "valid bearer authentication is required")
        parts = headers[0].split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
            raise APIError(401, "unauthenticated", "valid bearer authentication is required")
        principal = principals.get(hashlib.sha256(parts[1].encode()).digest())
        if principal is None:
            raise APIError(401, "unauthenticated", "valid bearer authentication is required")
        return principal

    async def authorized_task(request: Request, task_id: str):
        principal = authenticate(request)
        identity(task_id, "task_id")
        task = await run_in_threadpool(store.get_task, principal.tenant_id, task_id)
        if task["contract"]["repo_id"] not in principal.repositories:
            raise APIError(403, "repository_denied", "repository grant is required")
        return principal, task

    @app.get("/health")
    async def health():
        return {"configured": configured, "mode": "reference_api", "production_readiness": "unmeasured"}

    if readiness is not None:
        @app.get("/ready")
        async def ready():
            try:
                result = await run_in_threadpool(readiness)
                if not isinstance(result, dict) or type(result.get("ready")) is not bool:
                    raise ValueError("invalid readiness observation")
                return JSONResponse(result, status_code=200 if result["ready"] else 503)
            except Exception:
                return JSONResponse({"ready": False, "reason": "probe_failed",
                                     "production_readiness": "unmeasured"}, status_code=503)

    if contract_catalog is not None:
        @app.get("/catalog")
        async def catalog(request: Request):
            principal = authenticate(request)
            return await run_in_threadpool(contract_catalog, principal)

    @app.post("/tasks", status_code=202)
    async def submit(request: Request):
        principal = authenticate(request)
        body = await _body(request, {"key", "contract"})
        identity(body["key"], "submission key")
        if not isinstance(body["contract"], dict):
            raise APIError(422, "invalid_contract", "contract must be an object")
        repository = body["contract"].get("repo_id")
        if not isinstance(repository, str):
            raise APIError(422, "invalid_contract", "repo_id must be a string")
        if repository not in principal.repositories:
            raise APIError(403, "repository_denied", "repository grant is required")
        profile = body["contract"].get("profile", "production")
        if not isinstance(profile, str):
            raise APIError(422, "invalid_contract", "profile must be a string")
        if profile not in principal.profiles:
            raise APIError(403, "profile_denied", "execution profile grant is required")
        if contract_admission is not None:
            await run_in_threadpool(contract_admission, principal, body["contract"])
        return await run_in_threadpool(store.submit, principal.tenant_id, body["key"], body["contract"])

    @app.get("/tasks/{task_id}")
    async def status(request: Request, task_id: str):
        _principal, task = await authorized_task(request, task_id)
        return task

    @app.get("/tasks/{task_id}/snapshot")
    async def snapshot(request: Request, task_id: str):
        principal, _task = await authorized_task(request, task_id)
        return await run_in_threadpool(store.snapshot, principal.tenant_id, task_id)

    @app.get("/tasks/{task_id}/events")
    async def events(request: Request, task_id: str, cursor: str | None = None, limit: int = 100):
        principal, _task = await authorized_task(request, task_id)
        strict_int(limit, "event limit", 1, 1000)
        last_id = request.headers.get("last-event-id")
        if last_id and cursor and last_id != cursor:
            raise APIError(400, "ambiguous_cursor", "cursor and Last-Event-ID disagree")
        selected = last_id or cursor
        if selected is not None and len(selected) > 4096:
            raise APIError(422, "invalid_cursor", "event cursor is too large")
        page = await run_in_threadpool(store.events, principal.tenant_id, task_id, selected, limit)
        if "text/event-stream" not in request.headers.get("accept", ""):
            return page
        for event in page["events"]:
            if not isinstance(event.get("cursor"), str) or "\n" in event["cursor"] or "\r" in event["cursor"]:
                raise RuntimeError("trusted store event cursor is missing or unsafe")

        async def encoded():
            for event in page["events"]:
                # Each event's cursor reflects that row, never the page end.
                payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                yield f"id: {event['cursor']}\nevent: progress\ndata: {payload}\n\n"
            yield ": end of bounded page; reconnect with Last-Event-ID\n\n"

        return StreamingResponse(
            encoded(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/tasks/{task_id}/cancel")
    async def cancel(request: Request, task_id: str):
        principal, _task = await authorized_task(request, task_id)
        body = await _body(request, {"request_id"})
        identity(body["request_id"], "cancellation identity")
        return await run_in_threadpool(store.cancel, principal.tenant_id, task_id, body["request_id"])

    @app.get("/tasks/{task_id}/artifacts/{artifact_digest}")
    async def artifact(request: Request, task_id: str, artifact_digest: str):
        principal, _task = await authorized_task(request, task_id)
        digest(artifact_digest)
        if artifact_store is None:
            raise APIError(503, "artifacts_unconfigured", "artifact storage is not configured")
        await run_in_threadpool(store.authorize_artifact, principal.tenant_id, task_id, artifact_digest)
        try:
            data = await run_in_threadpool(artifact_store.get, principal.tenant_id, task_id, artifact_digest)
        except FileNotFoundError as error:
            raise NotFound("artifact not found") from error
        return Response(
            data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{artifact_digest}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/tasks/{task_id}/reviews/{review_id}")
    async def review(request: Request, task_id: str, review_id: str):
        principal, _task = await authorized_task(request, task_id)
        if not principal.can_review:
            raise APIError(403, "review_denied", "review permission is required")
        identity(review_id, "review_id")
        body = await _body(request, {"decision", "key"})
        identity(body["key"], "review key")
        if body["decision"] not in ("accepted", "rejected"):
            raise APIError(422, "invalid_review", "review decision must be accepted or rejected")
        return await run_in_threadpool(
            store.record_review,
            principal.tenant_id,
            task_id,
            review_id,
            principal.subject_id,
            body["decision"],
            body["key"],
        )

    return app
