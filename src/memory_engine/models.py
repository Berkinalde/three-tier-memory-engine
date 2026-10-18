"""Strict, dependency-free public data contracts."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from typing import Any

TIERS = ("working", "episodic", "semantic")


class MemoryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise MemoryError(code)


def utf8(value):
    try:
        return value.encode("utf-8")
    except UnicodeError:
        raise MemoryError("invalid_unicode") from None


def text_ok(value, maximum=256):
    return type(value) is str and bool(value.strip()) and len(utf8(value)) <= maximum


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise MemoryError("invalid_timestamp") from None
    require(
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None,
        "invalid_timestamp",
    )
    return value.astimezone(timezone.utc)


def json_value(value, depth=0):
    require(depth <= 12, "json_depth_limit")
    if type(value) is dict:
        for k, v in value.items():
            require(type(k) is str, "invalid_json")
            utf8(k)
            json_value(v, depth + 1)
    elif type(value) is list:
        for v in value:
            json_value(v, depth + 1)
    else:
        require(value is None or type(value) in (str, bool, int, float), "invalid_json")
        if type(value) is str:
            utf8(value)
        if type(value) is float:
            require(math.isfinite(value), "invalid_json")


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda v: v.isoformat() if isinstance(v, datetime) else asdict(v),
    )


@dataclass(frozen=True)
class Scope:
    tenant_id: str
    user_id: str

    def __post_init__(self):
        require(text_ok(self.tenant_id) and text_ok(self.user_id), "invalid_scope")


@dataclass(frozen=True)
class MemoryInput:
    tier: str
    content: str
    session_id: str | None = None
    task_id: str | None = None
    source_refs: list[str] = field(default_factory=list)
    occurred_at: datetime | None = None
    expires_at: datetime | None = None
    importance: float = 0.5
    confidence: float = 0.5
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    fact_key: str | None = None
    verification_status: str = "unverified"

    @classmethod
    def from_dict(cls, data):
        require(type(data) is dict, "object_required")
        require(set(data) <= cls.__dataclass_fields__.keys(), "unknown_field")
        try:
            return cls(**data)
        except TypeError:
            raise MemoryError("invalid_input") from None

    def validate(self, now):
        require(self.tier in TIERS, "invalid_tier")
        require(text_ok(self.content, 16384), "invalid_content")
        for value in (self.importance, self.confidence):
            require(type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value), "invalid_score")
        require(self.status in ("active", "candidate"), "invalid_status")
        require(self.verification_status in ("unverified", "verified"), "invalid_verification")
        require(
            type(self.source_refs) is list
            and len(self.source_refs) <= 64
            and all(text_ok(s) for s in self.source_refs),
            "invalid_sources",
        )
        require(type(self.metadata) is dict, "invalid_metadata")
        json_value(self.metadata)
        require(len(encode(self.metadata).encode()) <= 4096, "metadata_size_limit")
        for value in (self.session_id, self.task_id, self.fact_key):
            require(value is None or text_ok(value), "invalid_identifier")
        if self.tier == "working":
            require(text_ok(self.session_id) and text_ok(self.task_id), "working_scope_required")
        if self.tier == "semantic":
            require(text_ok(self.fact_key), "fact_key_required")
        else:
            require(
                self.verification_status == "unverified" and self.fact_key is None, "semantic_fields_only"
            )
        occurred, expires = timestamp(self.occurred_at), timestamp(self.expires_at)
        require(occurred is None or occurred <= now, "invalid_time_order")
        require(expires is None or expires > now, "expired_input")
        if self.verification_status == "verified":
            require(bool(self.source_refs), "verified_sources_required")


@dataclass(frozen=True)
class Memory:
    id: str
    tenant_id: str
    user_id: str
    tier: str
    content: str
    session_id: str | None
    task_id: str | None
    source_refs: list[str]
    created_at: datetime
    updated_at: datetime
    occurred_at: datetime | None
    expires_at: datetime | None
    importance: float
    confidence: float
    status: str
    version: int
    metadata: dict[str, Any]
    fact_key: str | None
    verification_status: str
    supersedes_id: str | None = None
    verified_at: datetime | None = None

    @classmethod
    def from_json(cls, payload):
        data = json.loads(payload)
        for key in ("created_at", "updated_at", "occurred_at", "expires_at", "verified_at"):
            data[key] = timestamp(data[key])
        return cls(**data)


@dataclass(frozen=True)
class RetrievalResult:
    id: str
    tier: str
    content: str
    source_refs: list[str]
    relevance: float
    recency: float
    importance: float
    final_score: float
    reason: str
