import pytest
from test_core import make, S
from memory_engine import Scope, MemoryInput, MemoryError
from memory_engine.adapters.embeddings import EmbeddingIndex, HashEmbedder


def test_hybrid_filters_and_delete(engine):
    a = make(engine)
    make(engine, tier="working")
    engine.create(Scope("t", "other"), MemoryInput(tier="episodic", content="IAM policy"))
    index = EmbeddingIndex(engine, HashEmbedder())
    assert index.index_scope(S) == 1
    assert [r.id for r in index.retrieve(S, "IAM")] == [a.id]
    engine.delete_memory(S, a.id)
    assert index.retrieve(S, "IAM") == []
    with engine.repo.connection() as db:
        assert db.execute("SELECT count(*) FROM embeddings").fetchone()[0] == 0


def test_model_change_and_content_change(engine):
    a = make(engine)
    index = EmbeddingIndex(engine, HashEmbedder())
    index.index_scope(S)
    changed = EmbeddingIndex(engine, HashEmbedder(model_id="new"))
    with pytest.raises(MemoryError, match="reindex_required"):
        changed.retrieve(S, "IAM")
    changed.index_scope(S)
    assert changed.retrieve(S, "IAM")[0].id == a.id
    engine.update(S, a.id, expected_version=1, changes={"content": "new IAM"})
    with pytest.raises(MemoryError, match="reindex_required"):
        changed.retrieve(S, "IAM")


@pytest.mark.parametrize("vector", [[0.0] * 32, [1.0], [float("nan")] * 32])
def test_invalid_vectors(engine, vector):
    make(engine)

    class Bad(HashEmbedder):
        def embed(self, text):
            return vector

    with pytest.raises(MemoryError, match="invalid_vector"):
        EmbeddingIndex(engine, Bad()).index_scope(S)


def test_provider_failure_atomic(engine):
    make(engine)

    class Bad(HashEmbedder):
        def embed(self, text):
            raise RuntimeError("secret response")

    with pytest.raises(MemoryError, match="embedding_provider_error"):
        EmbeddingIndex(engine, Bad()).index_scope(S)
    assert engine.retrieve(S, "IAM")


def test_hybrid_deterministic_and_empty(engine):
    make(engine)
    make(engine, "IAM permission")
    index = EmbeddingIndex(engine, HashEmbedder())
    index.index_scope(S)
    assert index.retrieve(S, "") == []
    a = index.retrieve(S, "IAM")
    assert a == index.retrieve(S, "IAM")
    assert all(0 <= r.relevance <= 1 and 0 <= r.final_score <= 1 for r in a)


def test_symbol_only_content_and_query_are_safe(engine):
    # Content with no word tokens (punctuation/symbol only) must not produce the zero vector
    # that validate_vector rejects, which previously failed indexing for the whole scope.
    make(engine, "!!!")
    make(engine, "IAM policy")
    index = EmbeddingIndex(engine, HashEmbedder())
    assert index.index_scope(S) == 2
    # A symbol-only query has nothing to match; it returns no results instead of erroring.
    assert index.retrieve(S, "???") == []
    assert [r.content for r in index.retrieve(S, "IAM")] == ["IAM policy"]
