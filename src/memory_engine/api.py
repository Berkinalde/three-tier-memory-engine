"""Optional FastAPI boundary. Authentication supplies scope; bodies never do."""

import hmac
import json
import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from .api_middleware import Limits, RequestLimits, error_response
from .models import Scope, MemoryInput, MemoryError, encode, require, json_value
from .repository import Repository
from .service import MemoryService


class BearerAuthenticator:
    """Small deployment adapter; use injected validated OIDC/JWT verifier at scale."""

    def __init__(self, token_scopes):
        if not token_scopes or any(
            not isinstance(k, str) or not k or not isinstance(v, Scope) for k, v in token_scopes.items()
        ):
            raise ValueError("invalid_token_config")
        self.token_scopes = dict(token_scopes)

    def __call__(self, request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 4096:
            raise MemoryError("unauthorized")
        token = auth[7:].encode()
        for expected, scope in self.token_scopes.items():
            if hmac.compare_digest(token, expected.encode()):
                return scope
        raise MemoryError("unauthorized")


def status_for(code):
    if code == "unauthorized":
        return 401
    if code == "not_found":
        return 404
    if code in (
        "version_conflict",
        "idempotency_conflict",
        "record_superseded",
        "record_expired",
        "operation_in_progress",
    ):
        return 409
    if code in ("quota_exceeded", "candidate_limit"):
        return 429
    return 422


def create_app(service, *, authenticator=None, development=False, limits=None):
    if authenticator is None and not development:
        raise ValueError("authenticator_required")
    app = FastAPI(
        title="Three-Tier Memory Engine", version="0.5.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.metrics = {
        "requests": 0,
        "errors": 0,
        "duration_seconds": 0.0,
        "duration_buckets": {".01": 0, ".05": 0, ".1": 0, ".5": 0, "1": 0, "5": 0, "inf": 0},
    }
    app.add_middleware(RequestLimits, limits=limits or Limits(), metrics=app.state.metrics)

    @app.exception_handler(MemoryError)
    async def memory_error(request, exc):
        return error_response(exc.code, status_for(exc.code), request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response("invalid_input", 422, request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(
            "not_found" if exc.status_code == 404 else "http_error", exc.status_code, request.state.request_id
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        return error_response("storage_unavailable", 503, request.state.request_id)

    async def identity(request: Request):
        if authenticator is not None:
            scope = await run_in_threadpool(authenticator, request)
            require(isinstance(scope, Scope), "unauthorized")
            return scope
        tenant, user = request.headers.get("X-Dev-Tenant"), request.headers.get("X-Dev-User")
        require(bool(tenant) and bool(user), "unauthorized")
        return Scope(tenant, user)

    async def body(request):
        try:
            data = json.loads(await request.body())
            json_value(data)
            require(type(data) is dict, "object_required")
            return data
        except (ValueError, UnicodeError, RecursionError):
            raise MemoryError("invalid_json") from None

    def response(result, status=200):
        return JSONResponse(json.loads(encode(result)), status_code=status)

    @app.get("/health")
    def health():
        with service.repo.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            db.execute("SELECT 1 FROM memories LIMIT 1").fetchone()
        return {"status": "ok", "schema_version": version}

    @app.post("/v1/memories", status_code=201)
    async def create(request: Request, scope=Depends(identity)):
        data = MemoryInput.from_dict(await body(request))
        result = await run_in_threadpool(
            service.create,
            scope,
            data,
            idempotency_key=request.headers.get("Idempotency-Key"),
            authority="user",
        )
        return response(result, 201)

    @app.post("/v1/memories/search")
    async def search(request: Request, scope=Depends(identity)):
        data = await body(request)
        require(
            set(data) <= {"query", "session_id", "task_id", "top_k", "tier_filters"} and "query" in data,
            "invalid_search",
        )
        return response(await run_in_threadpool(service.retrieve, scope, **data))

    @app.patch("/v1/memories/{identifier}")
    async def update(identifier: str, request: Request, scope=Depends(identity)):
        data = await body(request)
        require(set(data) == {"expected_version", "changes"}, "invalid_update")
        return response(await run_in_threadpool(service.update, scope, identifier, authority="user", **data))

    @app.delete("/v1/memories/{identifier}")
    async def delete(identifier: str, scope=Depends(identity)):
        return {"deleted": await run_in_threadpool(service.delete_memory, scope, identifier)}

    @app.delete("/v1/users/me/memories")
    async def delete_user(scope=Depends(identity)):
        return {"deleted": await run_in_threadpool(service.delete_user_data, scope)}

    return app


def app_from_env():
    """uvicorn memory_engine.api:app_from_env --factory --no-access-log."""
    development = os.environ.get("MEMORY_DEVELOPMENT") == "1"
    token_file = os.environ.get("MEMORY_TOKEN_FILE")
    auth = None
    if token_file:
        raw = json.loads(Path(token_file).read_text())
        auth = BearerAuthenticator({token: Scope(**scope) for token, scope in raw.items()})
    service = MemoryService(Repository(os.environ.get("MEMORY_DB", "data/memory.db")))
    return create_app(service, authenticator=auth, development=development)
