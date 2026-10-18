import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from memory_engine.models import Scope, MemoryInput, MemoryError
from memory_engine.repository import Repository
from memory_engine.service import MemoryService
from memory_engine.policies import Policy

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
S = Scope("t", "u")


def make(engine, content="IAM policy", tier="semantic", **kw):
    if tier == "working":
        kw = {"session_id": "s", "task_id": "task", **kw}
    if tier == "semantic":
        kw = {"fact_key": content, **kw}
    return engine.create(S, MemoryInput(tier=tier, content=content, **kw))


@pytest.mark.parametrize("tier", ["working", "episodic", "semantic"])
def test_persistence(engine, tier):
    a = make(engine, tier=tier)
    reopened = MemoryService(Repository(engine.repo.path), clock=lambda: NOW)
    assert reopened.get(S, a.id).content == a.content
    assert reopened.retrieve(S, "IAM", session_id="s", task_id="task")[0].id == a.id


def test_isolation(engine):
    make(engine, tier="working")
    for scope in [Scope("t2", "u"), Scope("t", "u2")]:
        assert engine.retrieve(scope, "IAM", session_id="s", task_id="task") == []
    assert engine.retrieve(S, "IAM") == []
    assert engine.retrieve(S, "IAM", session_id="other", task_id="task") == []
    assert len(engine.retrieve(S, "", session_id="s", task_id="task", tier_filters=["working"])) == 1
    assert engine.retrieve(S, "") == []


def test_expiry_boundary(engine):
    a = make(engine, tier="working")
    engine.test_clock[0] += timedelta(hours=24)
    assert engine.retrieve(S, "IAM", session_id="s", task_id="task") == []
    assert engine.expire(S) == 1
    with pytest.raises(MemoryError, match="not_found"):
        engine.get(S, a.id)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"importance": float("nan")},
        {"confidence": float("inf")},
        {"importance": True},
        {"content": ""},
        {"content": "a" * 17000},
        {"expires_at": NOW},
        {"occurred_at": NOW + timedelta(days=1)},
        {"metadata": {"n": float("nan")}},
        {"tier": "working"},
        {"fact_key": None},
        {"source_refs": "event"},
        {"expires_at": datetime(2026, 1, 1)},
        {"metadata": {"large": "a" * 5000}},
    ],
)
def test_validation(engine, kwargs):
    with pytest.raises(MemoryError):
        engine.create(S, MemoryInput(**{"tier": "semantic", "content": "text", "fact_key": "key", **kwargs}))


def test_scope_validation():
    with pytest.raises(MemoryError):
        Scope("", "u")


def test_idempotency(engine):
    inp = MemoryInput(tier="episodic", content="done")
    a = engine.create(S, inp, idempotency_key="once")
    engine.test_clock[0] += timedelta(hours=1)
    assert engine.create(S, inp, idempotency_key="once").id == a.id
    with pytest.raises(MemoryError, match="idempotency_conflict"):
        engine.create(S, MemoryInput(tier="episodic", content="different"), idempotency_key="once")
    assert engine.create(Scope("t", "other"), inp, idempotency_key="once").id != a.id
    assert engine.create(S, inp).id != a.id


def test_version_race(engine):
    a = make(engine)

    def attempt(i):
        svc = MemoryService(Repository(engine.repo.path), clock=lambda: NOW)
        try:
            return svc.update(S, a.id, expected_version=1, changes={"content": f"IAM {i}"}).version
        except MemoryError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(map(str, results)) == ["2", "version_conflict"]


def test_authority(engine):
    a = engine.create(
        S,
        MemoryInput(
            tier="semantic",
            content="Türkçe",
            fact_key="language",
            verification_status="verified",
            source_refs=["event:1"],
        ),
        authority="user",
    )
    b = engine.create(S, MemoryInput(tier="semantic", content="English", fact_key="language"))
    assert b.status == "candidate"
    assert engine.get(S, a.id).status == "active"
    c = engine.create(
        S,
        MemoryInput(
            tier="semantic",
            content="Deutsch",
            fact_key="language",
            verification_status="verified",
            source_refs=["event:2"],
        ),
        authority="user",
    )
    assert c.supersedes_id == a.id
    assert engine.get(S, a.id).status == "superseded"
    assert engine.retrieve(S, "Türkçe") == []
    with pytest.raises(MemoryError, match="authority_required"):
        engine.update(S, c.id, expected_version=1, changes={"content": "injected"})
    with pytest.raises(MemoryError, match="authority_required"):
        engine.create(
            S,
            MemoryInput(
                tier="semantic",
                content="bad",
                fact_key="x",
                verification_status="verified",
                source_refs=["e"],
            ),
        )


def test_quota_verified(tmp_path):
    e = MemoryService(
        Repository(tmp_path / "q.db"),
        clock=lambda: NOW,
        policy=Policy(max_records_per_tier=1, max_bytes_per_tier=20000, allow_eviction=True),
    )
    a = make(e, content="first", importance=0.1)
    b = make(e, content="second", importance=0.2)
    with pytest.raises(MemoryError, match="not_found"):
        e.get(S, a.id)
    e.update(
        S,
        b.id,
        expected_version=1,
        changes={"verification_status": "verified", "source_refs": ["e"]},
        authority="user",
    )
    with pytest.raises(MemoryError, match="quota_exceeded"):
        make(e, content="third")
    assert e.get(S, b.id).content == "second"


def test_quota_rollback(tmp_path):
    e = MemoryService(
        Repository(tmp_path / "q.db"),
        clock=lambda: NOW,
        policy=Policy(max_records_per_tier=2, max_bytes_per_tier=1500, allow_eviction=True),
    )
    a = make(e, content="short", importance=0.1)
    with pytest.raises(MemoryError, match="quota_exceeded"):
        make(e, content="long" * 600, fact_key="long")
    assert e.get(S, a.id).content == "short"


def test_unicode(engine):
    a = make(engine, "İSTANBUL ışık")
    b = make(engine, "istanbul ışık")
    make(engine, "unrelated", importance=1)
    results = engine.retrieve(S, "istanbul")
    assert [r.id for r in results] == sorted([a.id, b.id])
    assert all(0 <= r.final_score <= 1 for r in results)
    assert engine.retrieve(S, "totally missing") == []


def test_delete(engine):
    a = make(engine)
    engine.update(S, a.id, expected_version=1, changes={"content": "IAM new"})
    other = engine.create(Scope("t", "other"), MemoryInput(tier="episodic", content="IAM"))
    assert engine.delete_memory(S, a.id) == 1
    with engine.repo.connection() as db:
        assert db.execute("SELECT count(*) FROM versions WHERE memory_id=?", (a.id,)).fetchone()[0] == 0
    assert engine.delete_user_data(S) == 0
    assert engine.get(Scope("t", "other"), other.id)


def test_random_invariants(engine):
    rng = random.Random(42)
    for i in range(80):
        scope = Scope(f"t{rng.randrange(3)}", f"u{rng.randrange(3)}")
        engine.create(scope, MemoryInput(tier="episodic", content=f"IAM event {i}"))
    for t in range(3):
        for u in range(3):
            scope = Scope(f"t{t}", f"u{u}")
            rows = engine.retrieve(scope, "IAM", top_k=3)
            assert len(rows) <= 3
            assert all(engine.get(scope, r.id).status == "active" for r in rows)


def test_cli_restart(tmp_path):
    env = {**os.environ, "PYTHONPATH": "src"}
    cmd = [
        sys.executable,
        "-m",
        "memory_engine",
        "--db",
        str(tmp_path / "cli.db"),
        "--tenant",
        "t",
        "--user",
        "u",
    ]
    p = subprocess.run(
        cmd + ["create"],
        input=json.dumps({"tier": "episodic", "content": "IAM done"}),
        text=True,
        capture_output=True,
        env=env,
    )
    assert p.returncode == 0, p.stderr
    a = json.loads(p.stdout)
    p = subprocess.run(cmd + ["search", "IAM"], text=True, capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)[0]["id"] == a["id"]
