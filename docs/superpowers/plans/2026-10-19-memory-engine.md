# Three-Tier Memory Engine Implementation Plan

> Execution: superpowers:executing-plans, test-first, continuous execution authorized by user.

**Goal:** V1–V5 yerel, kalıcı ve kapsam yalıtımlı agent hafızasını tamamlamak.
**Architecture:** Bağımsız stdlib çekirdeği; SQLite repository transaction sınırı; service politikaları; bağımsız assembler, embedding ve extraction adaptörleri; isteğe bağlı FastAPI.
**Tech Stack:** Python >=3.11, SQLite, pytest, FastAPI.
**Spec:** docs/requirements.md (read-only original: /Users/berkinaldemir/Desktop/three-tier-memory-engine.md)

## Global Constraints
- sources/ ve mevcut assembler dosyaları salt okunur; yeni çalışma ayrı klasörde.
- tenant/user her sorgudan önce SQL'de filtrelenir; working için session/task gerekir.
- Ağsız testler; ücretli servis ve bulut yayını yok. Canlı kalite iddiası yok.
- Türkçe README; İngilizce kod. UTC aware zaman; enjekte clock.

## Review Focus
- Malformed/nested JSON and numeric coercion must produce stable errors.
- Failed quota/update/extraction writes must not damage prior data.
- Delete and expiry of sources must invalidate derived records transitively.
- Concurrent version updates/idempotency must have exactly one winner.
- Authentication, request limits and dependency failure must not leak content.

## Task 1 — V1 core and CLI
Files: models.py, policies.py, repository.py, retrieval.py, service.py, migrations/001.sql, cli.py; tests/test_core.py.
Interfaces: Scope(tenant_id,user_id); MemoryInput(...); MemoryService(repo,clock,policy); create(scope,input,idempotency_key,authority), get, update(expected_version), retrieve(scope,query,session_id,task_id,top_k,tier_filters), expire, delete_memory, delete_user_data.
- [x] Write/run failing persistence, validation, isolation, expiry, version race, idempotency, conflicts, quota rollback, deletion, Unicode and CLI tests.
- [x] Implement transactional core and bounded deterministic retrieval.
- [x] Run entire pytest suite and record evidence.

## Task 2 — V2 actual assembler adapter
Files: adapters/context_assembler.py, examples/two_sessions.py; tests/test_assembler.py.
Interfaces: assemble_memories(results,query,budget,assembler,counter=None,max_items=100,max_bytes=65536) -> assembly with source mapping and decisions.
- [x] Test real ../dynamic-context-assembler/src API, required=False, preservation of sources and byte/item/token limits.
- [x] Implement adapter and subprocess restart demo with deletion.
- [x] Run suite and demo, record evidence.

## Task 3 — V3 embeddings
Files: adapters/embeddings.py; tests/test_embeddings.py.
Interfaces: Embedder protocol(model_id,version,dimension,embed); EmbeddingIndex(service,embedder).index_scope/retrieve; offline HashEmbedder.
- [x] Failing tests for filtered candidates, invalid vectors, model/content drift, deletion, provider failure.
- [x] Implement bounded cosine and deterministic normalized RRF; scoped vectors with cascading deletion.
- [x] Run suite and lexical/hybrid fixtures.

## Task 4 — V4 explicit extraction
Files: adapters/extraction.py; tests/test_extraction.py.
Interfaces: ExtractionService(service,provider,enabled=False).process(scope,source_ids,operation_id).
- [x] Test schema, grounding, source provenance, secret rejection, contradiction, timeout, idempotency and source invalidation.
- [x] Implement one-call bounded async provider, strict schema, exact-source evidence validation, atomic candidate writes.
- [x] Run suite; document mock-only quality limits.

## Task 5 — V5 HTTP, operations and evaluation
Files: api.py, api_middleware.py, Dockerfile, scripts/, .github/workflows/, evaluations/, README.md, docs/runbook.md.
Interfaces: create_app(service,authenticator,development=False,...).
- [x] Test authenticated scope, 404 uniformity, 409/413/422/429, streaming size bounds, concurrency, content-free logging.
- [x] Implement API and operations; versioned synthetic evaluation and newest-first baseline.
- [x] Run full suite, lint, real assembler demo, evaluation, HTTP/container smoke if runtime available.
- [x] Independent final review and regressions for material findings; final evidence and limitations.

## Verification limitation
V5 container build/health/restart remains pending: Docker engine did not respond to two 15-second bounded checks. Code, local HTTP, tests, packaging and runbook are delivered; remote CI and live provider quality are not claimed.
