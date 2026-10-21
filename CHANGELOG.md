# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
semantic versioning.

## [0.5.1] - 2026-10-22

### Fixed

- Token-less (symbol-only) content and queries no longer produce a zero vector
  that breaks hybrid indexing; `HashEmbedder` falls back to a deterministic
  non-zero vector. Regression: `test_symbol_only_content_and_query_are_safe`.
- Version history no longer makes a frequently updated record permanently
  un-updatable. Quota pressure now reclaims the oldest version payloads before
  eviction, while the live payload stays in `memories`. Regression:
  `test_version_history_does_not_brick_updates`.
- Search rate limiting is now per principal (bearer-token hash, falling back to
  the client host) instead of a global pre-auth counter, so an unauthenticated
  caller cannot exhaust valid callers' budget. Regression:
  `test_search_rate_limit_is_per_principal`.
- A cycle attempt during `update` now returns `source_cycle` instead of the
  misleading `not_found`; the check runs before descendants are deleted.
  Regression: `test_update_cycle_reports_source_cycle`.
- `candidates` now truncates at `max_candidates` instead of failing the whole
  search with `candidate_limit`, keeping a full scope searchable. Regression:
  `test_candidate_limit_truncates_instead_of_failing`.
- The public test suite skips the optional `dynamic-context-assembler`
  integration when the sibling package is unavailable (`pytest.importorskip`),
  and CI treats that checkout as non-fatal.

### Changed

- README status reflects the successful GitHub Actions runs (Python 3.11/3.13
  matrix and container smoke) and links the public documentation set.
- Version bumped to 0.5.1.

### Verification

- 81 tests pass; `ruff check` and `ruff format --check` are clean.
- `offline-tests` workflow is green on `main`.

## [0.5.0] - 2026-10-19

### Added

- Initial three-tier memory engine: models, policies, retrieval, SQLite
  repository, service, adapters (context assembler, embeddings, extraction),
  HTTP API, CLI, tests, evaluations, and documentation.
