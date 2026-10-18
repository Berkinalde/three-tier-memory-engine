import json
import sqlite3
import pytest
from test_core import S, make
from test_extraction import Provider, run
from memory_engine import Repository, MemoryError
from memory_engine.adapters.extraction import ExtractionService


def test_v1_migration_preserves_output_invalidation(engine):
    source = make(engine, "Türkçe tercih", tier="episodic")
    ids = run(ExtractionService(engine, Provider(), enabled=True), [source.id])
    with engine.repo.connection(write=True) as db:
        db.execute("DROP TABLE operation_outputs")
        db.execute("PRAGMA user_version=1")
    Repository(engine.repo.path)
    assert engine.get(S, source.id).content == source.content
    engine.delete_memory(S, ids[0])
    with engine.repo.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(MemoryError, match="unsupported_schema"):
        Repository(path)


def test_cached_operation_eviction_never_returns_missing_ids(engine):
    source = make(engine, "Türkçe tercih", tier="episodic")
    svc = ExtractionService(engine, Provider(), enabled=True)
    ids = run(svc, [source.id])
    with engine.repo.connection(write=True) as db:
        engine.repo.delete_ids(db, S, [ids[1]])
    result = run(svc, [source.id])
    assert all(engine.get(S, i) for i in result)
    assert ids[1] not in result


def test_evaluation_fixture_integrity():
    from pathlib import Path

    fixture = json.loads(Path("evaluations/corpus-v1.json").read_text())
    labels = {r["label"] for r in fixture["records"]}
    assert len(labels) == len(fixture["records"])
    assert all(set(q["expected"]) <= labels for q in fixture["queries"])
