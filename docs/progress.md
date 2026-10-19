# Execution ledger — 2026-10-19-memory-engine
Spec: /Users/berkinaldemir/Desktop/three-tier-memory-engine.md
Ruling: New standalone directory because project inherits an unrelated home-directory Git repository; no standalone project repository exists; existing assembler stays read-only. No worktree needed.
Ruling: Continuous inline execution; user explicitly waived approval checkpoints.
Pre-flight: V2–V5 consume the Scope, Memory and RetrievalResult interfaces in V1. Actual assembler accepts working_memory items and preserves additional fields; adapter will pass provenance there and in source_mapping.
V1: 28 core/CLI tests pass. Red import stage recorded; WAL initialization failure traced to transaction and fixed. Test fixtures corrected for unrelated user's version and identifier bounds. SQLite source changes invalidate descendants. Quota counts version payload history.
V2: Real assembler integration, source mapping and budget tests pass; subprocess restart demo saved evaluations/demo.json. Small-budget demo calibrated against actual counter to 135 tokens.
V3: 37 total tests pass, including hybrid filtering, model/content reindex, zero/dimension/NaN vectors, provider errors and delete cascade. Hash embedder is offline plumbing only.
V4: 52 total tests passed before V5; exact-source excerpts are deliberately conservative. Source content is untrusted; no live provider used.
V5: 63 tests initially passed; HTTP authenticated scopes, body streaming limit, concurrency, global search rate limit and content-free metrics verified.
Final independent review: four important issues, no minors. Added 8 failing regressions, then fixed Unicode/oversized scores, operation output invalidation, claim ownership and atomic batch quota. Whole suite: 71 passed; ruff passed.
Ruling: Operation output links require schema migration 002; migration runner now applies each migration within a single write transaction and rejects newer schemas.
Ruling: An isolated project directory is used without modifying the unrelated home-directory Git repository. No commits/push/publish performed.
Additional verification: migration 001→002 operation-output backfill and episodic source occurred_at preserved (2 regressions RED→GREEN). Final whole suite 76 passed, Ruff and formatting clean.
Final: Python 3.11 core smoke passed; actual loopback authenticated HTTP CRUD passed; standalone wheel build passed.
Final: Docker access granted outside sandbox, but two bounded checks timed out after 15s. V5 container health/restart verification remains pending; no image build or live provider claim.
Final: source/tests/docs preserved in separate project folder; no interaction with home-directory Git or synced sources. No deferred minor review findings.
Second review: five findings reproduced and fixed on branch review/fixes-2026-10-19 (token-less embedding zero vector, unbounded version-history quota, pre-auth search rate limit, misleading cycle error, hard candidate limit). 81 tests pass, Ruff clean. Three low-severity doc/integration notes documented without behavior change.
