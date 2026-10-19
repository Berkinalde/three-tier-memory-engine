import asyncio
import json
import logging
import httpx
import pytest
from fastapi.testclient import TestClient
from memory_engine import Scope
from memory_engine.api import create_app, BearerAuthenticator
from memory_engine.api_middleware import Limits


@pytest.fixture
def app(engine):
    return create_app(
        engine, authenticator=BearerAuthenticator({"token-a": Scope("t", "a"), "token-b": Scope("t", "b")})
    )


def client(app, token="token-a"):
    return TestClient(app, headers={"Authorization": "Bearer " + token})


def test_authentication_scope_and_errors(app):
    c = client(app)
    assert TestClient(app).post("/v1/memories/search", json={"query": "IAM"}).status_code == 401
    a = c.post("/v1/memories", json={"tier": "episodic", "content": "IAM"})
    assert a.status_code == 201, a.text
    identifier = a.json()["id"]
    assert (
        c.post("/v1/memories", json={"tier": "episodic", "content": "x", "user_id": "b"}).status_code == 422
    )
    other = client(app, "token-b")
    assert other.post("/v1/memories/search", json={"query": "IAM"}).json() == []
    for ident in [identifier, "missing"]:
        response = other.patch(
            "/v1/memories/" + ident, json={"expected_version": 1, "changes": {"content": "changed"}}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert response.json()["error"]["request_id"]
    assert (
        c.patch(
            "/v1/memories/" + identifier, json={"expected_version": 2, "changes": {"content": "changed"}}
        ).status_code
        == 409
    )
    assert c.delete("/v1/users/me/memories").json()["deleted"] == 1
    assert c.get("/health").json() == {"status": "ok", "schema_version": 2}


def test_idempotency(app):
    c = client(app)
    headers = {"Idempotency-Key": "once"}
    data = {"tier": "episodic", "content": "test"}
    a = c.post("/v1/memories", json=data, headers=headers)
    b = c.post("/v1/memories", json=data, headers=headers)
    assert a.json()["id"] == b.json()["id"]
    data["content"] = "other"
    assert c.post("/v1/memories", json=data, headers=headers).status_code == 409


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"tier": [], "content": "x"},
        {"tier": "semantic", "content": "x", "fact_key": {}},
        {"tier": "episodic", "content": "x", "importance": True},
        {"tier": "episodic", "content": "x", "metadata": {"deep": float("nan")}},
    ],
)
def test_invalid_input_stable_error(app, data):
    r = client(app).post(
        "/v1/memories", content=json.dumps(data), headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422, r.text
    assert set(r.json()["error"]) == {"code", "request_id"}


def test_body_stream_and_search_rate_limits(engine):
    app = create_app(engine, development=True, limits=Limits(max_body_bytes=100, searches_per_minute=1))
    c = TestClient(app, headers={"X-Dev-Tenant": "t", "X-Dev-User": "u"})
    assert c.post("/v1/memories", content=b"a" * 101).status_code == 413
    assert c.post("/v1/memories/search", json={"query": "IAM"}).status_code == 200
    assert c.post("/v1/memories/search", json={"query": "IAM"}).status_code == 429

    async def streaming():
        async def chunks():
            yield b"a" * 60
            yield b"b" * 60

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as ac:
            return await ac.post("/v1/memories", content=chunks())

    assert asyncio.run(streaming()).status_code == 413


def test_production_requires_authenticator(engine):
    with pytest.raises(ValueError, match="authenticator_required"):
        create_app(engine)


def test_logs_no_content_and_metrics(app, caplog):
    c = client(app)
    with caplog.at_level(logging.INFO, logger="memory_engine.http"):
        c.post("/v1/memories", json={"tier": "episodic", "content": "SENSITIVE-CONTENT-123"})
        c.post("/v1/memories/search", json={"query": "SENSITIVE-CONTENT-123"})
        c.delete("/v1/memories/SENSITIVE-ID-123")
    assert "SENSITIVE" not in caplog.text
    assert "token-a" not in caplog.text
    assert app.state.metrics["requests"] == 3
    assert app.state.metrics["errors"] == 1
    assert app.state.metrics["duration_seconds"] >= 0


def test_concurrency_bound(engine):
    app = create_app(engine, development=True, limits=Limits(max_concurrency=1))

    async def exercise():
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def body():
            entered.set()
            await gate.wait()
            yield b"{}"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as ac:
            first = asyncio.create_task(ac.post("/v1/memories", content=body()))
            await entered.wait()
            second = await ac.get("/health")
            gate.set()
            await first
            return second

    assert asyncio.run(exercise()).status_code == 429


@pytest.mark.parametrize(
    "data",
    [
        {"tier": "episodic", "content": "x", "importance": 10**400},
        {"tier": "episodic", "content": "\ud800"},
        {"tier": "episodic", "content": "x", "metadata": {"text": "\ud800"}},
    ],
)
def test_review_malformed_boundaries(app, data):
    c = client(app)
    r = c.post("/v1/memories", content=json.dumps(data))
    assert r.status_code == 422, r.text
    assert c.post("/v1/memories/search", json={"query": "x"}).json() == []


def test_review_query_surrogate_and_update_huge_score(app):
    c = client(app)
    a = c.post("/v1/memories", json={"tier": "episodic", "content": "x"}).json()
    assert c.post("/v1/memories/search", content=json.dumps({"query": "\ud800"})).status_code == 422
    assert (
        c.patch(
            "/v1/memories/" + a["id"],
            content=json.dumps({"expected_version": 1, "changes": {"confidence": 10**400}}),
        ).status_code
        == 422
    )


def test_search_rate_limit_is_per_principal(engine):
    app = create_app(
        engine,
        authenticator=BearerAuthenticator({"good": Scope("t", "u")}),
        limits=Limits(searches_per_minute=1),
    )
    anonymous = TestClient(app)
    valid = TestClient(app, headers={"Authorization": "Bearer good"})
    # An unauthenticated search must not consume another principal's search budget.
    assert anonymous.post("/v1/memories/search", json={"query": "x"}).status_code == 401
    assert valid.post("/v1/memories/search", json={"query": "x"}).status_code == 200
    assert valid.post("/v1/memories/search", json={"query": "x"}).status_code == 429
