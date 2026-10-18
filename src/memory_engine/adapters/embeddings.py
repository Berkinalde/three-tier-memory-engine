"""Offline deterministic plumbing; hash vectors are not a semantic quality model."""

from hashlib import sha256
import json
import math
from typing import Protocol
from ..models import MemoryError, encode, require, text_ok
from ..retrieval import lexical, scored, tokens


class Embedder(Protocol):
    model_id: str
    version: str
    dimension: int

    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    def __init__(self, model_id="offline-hash", version="1", dimension=32):
        self.model_id, self.version, self.dimension = model_id, version, dimension

    def embed(self, text):
        vector = [0.0] * self.dimension
        for token in sorted(tokens(text)):
            digest = sha256(token.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        return vector


def validate_vector(vector, dimension):
    require(type(vector) is list and len(vector) == dimension, "invalid_vector")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in vector), "invalid_vector")
    norm = math.hypot(*vector)
    require(math.isfinite(norm) and norm > 0, "invalid_vector")
    return [v / norm for v in vector]


def content_hash(text):
    return sha256(text.encode()).hexdigest()


class EmbeddingIndex:
    def __init__(self, service, embedder, *, min_cosine=0.25):
        self.service, self.embedder = service, embedder
        require(text_ok(embedder.model_id) and text_ok(embedder.version), "invalid_embedder")
        require(type(embedder.dimension) is int and 1 <= embedder.dimension <= 4096, "invalid_embedder")
        require(
            type(min_cosine) in (int, float) and math.isfinite(min_cosine) and 0 < min_cosine <= 1,
            "invalid_cosine_threshold",
        )
        self.min_cosine = min_cosine

    def _embed(self, text):
        try:
            value = self.embedder.embed(text)
        except Exception:
            raise MemoryError("embedding_provider_error") from None
        return validate_vector(value, self.embedder.dimension)

    def index_scope(self, scope, **filters):
        records = self.service.candidates(scope, **filters)
        # Provider work happens before transaction; re-read version before saving.
        vectors = [(record, self._embed(record.content)) for record in records]
        with self.service.repo.connection(write=True) as db:
            current = {r.id: r for r in self.service.candidates(scope, db=db, **filters)}
            for record, vector in vectors:
                require(
                    record.id in current and current[record.id].version == record.version, "index_conflict"
                )
                db.execute(
                    "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?,?,?)",
                    (
                        record.id,
                        self.embedder.model_id,
                        self.embedder.version,
                        self.embedder.dimension,
                        content_hash(record.content),
                        encode(vector),
                    ),
                )
        return len(vectors)

    def retrieve(self, scope, query, *, top_k=10, **filters):
        self.service.validate_query(query, top_k)
        if not query.strip():
            return self.service.retrieve(scope, query, top_k=top_k, **filters)
        with self.service.repo.connection() as db:
            # Candidates are SQL-scoped BEFORE vector rows are read or scored.
            records = self.service.candidates(scope, db=db, **filters)
            if not records:
                return []
            vectors = {}
            for record in records:
                row = db.execute("SELECT * FROM embeddings WHERE memory_id=?", (record.id,)).fetchone()
                require(row is not None, "reindex_required")
                require(
                    (row["model_id"], row["model_version"], row["dimension"], row["content_hash"])
                    == (
                        self.embedder.model_id,
                        self.embedder.version,
                        self.embedder.dimension,
                        content_hash(record.content),
                    ),
                    "reindex_required",
                )
                vectors[record.id] = validate_vector(json.loads(row["vector"]), self.embedder.dimension)
        query_vector = self._embed(query)
        lexical_scores = {r.id: lexical(query, r.content) for r in records}
        vector_scores = {r.id: sum(a * b for a, b in zip(query_vector, vectors[r.id])) for r in records}
        lexical_ids = sorted(
            (i for i, s in lexical_scores.items() if s >= self.service.policy.min_relevance),
            key=lambda i: (-lexical_scores[i], i),
        )
        vector_ids = sorted(
            (i for i, s in vector_scores.items() if s >= self.min_cosine),
            key=lambda i: (-vector_scores[i], i),
        )
        # RRF k=60, normalized by theoretical maximum 2/(60+1).
        fusion = {}
        for ranking in (lexical_ids, vector_ids):
            for rank, identifier in enumerate(ranking, 1):
                fusion[identifier] = fusion.get(identifier, 0.0) + 1 / (60 + rank)
        result = [
            scored(
                r,
                fusion[r.id] / (2 / 61),
                self.service.now(),
                self.service.policy,
                "hybrid_rrf_k60; lexical_rank="
                + str(lexical_ids.index(r.id) + 1 if r.id in lexical_ids else None)
                + "; vector_rank="
                + str(vector_ids.index(r.id) + 1 if r.id in vector_ids else None),
            )
            for r in records
            if r.id in fusion and fusion[r.id] / (2 / 61) >= self.service.policy.min_relevance
        ]
        return sorted(result, key=lambda r: (-r.final_score, r.id))[:top_k]
