# NoSpoilers Implementation Plan

> Execute inline using the executing-plans skill. User supplied the complete specification and authorized routine decisions and uninterrupted implementation.

**Goal:** A local, single-user movie picker with controlled disclosure and persistent learning.
**Architecture:** Python standard-library HTTP server, SQLite, static browser client. Explicit public serializers separate private imports/features from viewing responses. A reusable selector consumes finite candidates; reference ranker runs without credentials.
**Tech Stack:** Python 3.12 (validated 3.12.14), SQLite, HTML/CSS/JavaScript; unittest. No runtime third-party dependencies.
**Spec:** User's pasted handoff; summarized contract in docs/contracts.md.

## Global Constraints
- Never deliver private narrative/features/rationale to the viewing browser or normal logs.
- Fictional demo catalog and optional synthetic history remain separate from real data.
- No actual Jev API supplied: reference selector working; Jev integration pending.
- Existing cloud checkout is isolated; no worktree needed.

## Review Focus
- Invalid imports must be atomic and must not leak source strings in errors.
- Malicious watch links and unknown metadata must fail closed.
- Stale availability, future timestamps, incompatible feature versions must be excluded as appropriate.
- Ratings update rather than duplicate; unrated watched titles remain excluded.
- Session exclusions must never become persistent dislikes.

### Task 1: Private data, eligibility, selector
Files: nospoilers/core.py, nospoilers/store.py, tests/test_core.py.
- [x] Write and run failing tests for import, constraints, personalization, abstention, output validation, allowlist, persistence.
- [x] Implement versioned profiles, transactional import/history, bounded reference scoring, exact serializer.
- [x] Run unittest suite.

### Task 2: Extraction and source adapters
Files: nospoilers/adapters.py, tests/test_adapters.py, examples/*.json.
- [x] Test cache/version, instruction-shaped inputs, malformed extractor output, metadata ingestion failures.
- [x] Implement cached fixture/subprocess extractor and optional TMDB metadata ingestion with scoped HTTPS requests.
- [x] Run suite; exercise credential-free fixtures. Real Jev and model extraction remain pending absent dependencies.

### Task 3: Browser and server
Files: nospoilers/server.py, nospoilers/__main__.py, nospoilers/static/*, tests/test_http.py.
- [x] Write and run failing API/disclosure/end-to-end tests.
- [x] Implement local-only HTTP API and responsive UI: demo/import, onboarding/history, saved constraints, pick/another/reset, feedback, diagnostics.
- [x] Run full suite and real-browser workflow, including restart/persistence and canary checks.

### Task 4: Documentation and environment
Files: README.md, docs/contracts.md, docs/verification.md, .gitignore.
- [x] Document imports, scoring, extraction, startup, security boundary and pending integrations.
- [ ] Save startup instructions in environment draft: blocked by INVALID_ARGUMENT on save and draft reads; tested fallback retained in docs/cloud-start.md. No install script needed.
- [x] Review changes, run full tests and publish-ready report; do not publish or push.

## Execution record

Tasks 1–3 complete. Final verification: 29 unittest tests and Chromium acceptance passed, with 43 browser responses checked and real process restart. Fresh review findings fixed with regression tests; no deferred findings. Task 4 documentation and current-instance startup complete; reusable draft persistence remains externally blocked. The user subsequently requested committing and pushing the completed application to the repository. Environment configuration publication remains unverified.
