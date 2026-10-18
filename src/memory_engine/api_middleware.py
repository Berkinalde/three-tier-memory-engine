"""Pure ASGI body/concurrency/rate limits and content-free aggregate telemetry."""

import asyncio
from dataclasses import dataclass
import logging
import time
from uuid import uuid4
from starlette.responses import JSONResponse
from .models import require

logger = logging.getLogger("memory_engine.http")


@dataclass(frozen=True)
class Limits:
    max_body_bytes: int = 65536
    max_concurrency: int = 16
    searches_per_minute: int = 120
    body_timeout_seconds: float = 10.0

    def __post_init__(self):
        for value in (self.max_body_bytes, self.max_concurrency, self.searches_per_minute):
            require(type(value) is int and value > 0, "invalid_http_limits")
        require(
            type(self.body_timeout_seconds) in (int, float) and 0 < self.body_timeout_seconds <= 120,
            "invalid_http_limits",
        )


def error_response(code, status, request_id):
    return JSONResponse(
        {"error": {"code": code, "request_id": request_id}},
        status_code=status,
        headers={"X-Request-ID": request_id},
    )


class RequestLimits:
    def __init__(self, app, *, limits, metrics):
        self.app, self.limits, self.metrics = app, limits, metrics
        self.active = 0
        self.search_count = 0
        self.window_start = time.monotonic()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.monotonic()
        status = 500
        admitted = False
        started = False

        async def wrapped_send(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ] + [(b"x-request-id", request_id.encode())]
            await send(message)

        async def fail(code, code_status):
            await error_response(code, code_status, request_id)(scope, receive, wrapped_send)

        try:
            if self.active >= self.limits.max_concurrency:
                return await fail("concurrency_limit", 429)
            self.active += 1
            admitted = True
            lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
            if lengths:
                try:
                    length = int(lengths[0])
                except ValueError:
                    return await fail("invalid_content_length", 422)
                if len(lengths) != 1 or length < 0:
                    return await fail("invalid_content_length", 422)
                if length > self.limits.max_body_bytes:
                    return await fail("body_too_large", 413)
            body = bytearray()
            deadline = start + self.limits.body_timeout_seconds
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0.0, deadline - time.monotonic()))
                except TimeoutError:
                    return await fail("body_timeout", 408)
                if message["type"] == "http.disconnect":
                    status = 499
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.limits.max_body_bytes:
                    return await fail("body_too_large", 413)
                if not message.get("more_body", False):
                    break
            if scope["path"] == "/v1/memories/search":
                now = time.monotonic()
                if now - self.window_start >= 60:
                    self.window_start, self.search_count = now, 0
                if self.search_count >= self.limits.searches_per_minute:
                    return await fail("search_rate_limit", 429)
                self.search_count += 1
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, wrapped_send)
        except Exception:
            if not started:
                await fail("internal_error", 500)
            # Never log exception text: provider/SQL errors can contain inputs.
        finally:
            if admitted:
                self.active -= 1
            elapsed = time.monotonic() - start
            self.metrics["requests"] += 1
            self.metrics["errors"] += int(status >= 400)
            self.metrics["duration_seconds"] += elapsed
            for boundary in self.metrics["duration_buckets"]:
                if elapsed <= float(boundary):
                    self.metrics["duration_buckets"][boundary] += 1
            logger.info(
                '{"request_id":"%s","status":%d,"duration_ms":%.3f}', request_id, status, elapsed * 1000
            )
