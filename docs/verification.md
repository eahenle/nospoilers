# Verification record

Validation performed November 8, 2026, using only fictional/synthetic content. No genuine viewer history was supplied or created.

## Commands and results

- `python -m unittest discover -s tests -v`: **29 tests passed** after review fixes. Exercises real SQLite transactions/reopening, local HTTP, command protocol subprocesses, constraints, output validation, safe errors, reference fallback recording, ratings and skips, import atomicity, schema/number boundaries, extraction caching, and canary disclosure. Test count excludes browser acceptance.
- `PYTHONPATH=. python tests/browser_check.py`: **passed** with system Chromium. Started and restarted the actual CLI server with a temporary SQLite database. Loaded the separate fictional demo; added three seen-title ratings; picked, requested another without creating feedback, recorded post-watch feedback, restarted, retained four watched records, enforced an empty runtime-constrained pool, reset skips, then marked the current pick watched from history and verified it was invalidated. Final history count five. Inspected **43 responses** for a distinctive private canary; checked rendered markup, local storage and server logs. No browser JavaScript errors or external browser requests. Mobile width 390px had no horizontal overflow. Screenshots: ignored `.data/artifacts/desktop.png` and `mobile.png`.
- CLI import of `examples/demo.json`, two fixture extraction runs, `examples/demo-history.json`, and `examples/import-template.json`: completed using an isolated `/tmp` database. Automated test confirms 12 cache entries remain 12 after rerun and normal selection cannot invoke extraction.
- `python -m compileall -q nospoilers`, `node --check nospoilers/static/app.js`, `git diff --check`: passed.
- Current-instance server started with `python -m nospoilers serve` on port 8000. Functional local requests returned HTTP 200 for the UI and personal state. The personal catalog/history remained empty; no synthetic data was added to real use.

Toolchain: Python **3.12.14**, SQLite **3.53.1**, optional Playwright **1.62.0**, system Chromium **156.0.8078.79**. Playwright’s separate bundled Chromium was absent; the acceptance check used `/usr/bin/chromium` successfully.

## Review

A fresh reviewer inspected source and contracts, ran the then-current 24-test suite, and found no Critical issues. Its Important findings (explicit null private profiles; stale current pick after history updates) received failing regression tests and fixes. Blank/bare URL query parameters, oversized numeric features, malformed provider payloads, and a separately discovered non-string history ID failure also received regression coverage and bounded handling. The final suite and browser checks passed after these changes. No identified findings remain deferred.

## Timing and quality limits

A local synthetic microbenchmark made 20 reference-selector calls over the 12-film fictional catalog with three synthetic reactions. Median measured selector time **0.0647 ms**, maximum **0.1896 ms**; this excludes HTTP, SQLite queries and browser rendering. Reference selection made zero network/model calls. These are tiny-fixture current-machine measurements, not an end-to-end performance guarantee or an advantage over Jev. No paid API was called; no cost comparison is supported.

Personalization tests establish that changing an existing synthetic rating changes the chosen ID in a designed feature fixture, including seen-title profiles retained outside the unseen candidate pool. They do not establish recommendation quality for a real person. No genuine held-out evaluation is possible without genuine feedback.

The November 8 delivery used the reference selector and tested the external selector subprocess with a protocol fixture. Real model-backed extraction and live authenticated TMDB ingestion remain unverified. The local tests cover normalization, caching, and failure handling.

## Reusable environment configuration

The onboarding save API returned `INVALID_ARGUMENT`; draft reads also returned `INVALID_ARGUMENT`. No startup-field persistence or publication was confirmed. Runtime status reports this selected instance running with current enforced network policy. [cloud-start.md](cloud-start.md) retains the tested startup instructions for environment settings. No runtime install script is needed because the application has no external runtime dependencies. No network, secret, or repository-membership settings were changed. New-task snapshot restoration has not been tested.

## Mode-switch reaction isolation

The UI removes old history controls immediately when switching modes, binds each
history/search reaction row to its originating mode, and ignores a completed
old-mode reaction before it can clear a new-mode pick. Pending search results also retain their originating mode before
creating reaction controls, including programmatic demo switches. This prevents a retained
demo row from writing a reaction into personal history when catalog IDs overlap.

Run `node --test tests/test_mode_isolation.mjs` (Node.js 18+) for five focused
regressions executing the actual UI script with DOM/transport fixtures. Three fail before their corresponding fixes. These are not browser-rendering tests. The optional
real-browser scenario is `PYTHONPATH=. python tests/browser_mode_isolation.py`;
it uses a temporary fictional database and delayed state refresh. Chromium could
not launch in the repair environment because socket creation was restricted, so
that scenario and the existing browser acceptance suite remain unverified for
this change. The full Python unittest suite passes (29 tests).

## Hosted Jev adapter, November 12, 2026

- `python -m unittest discover -s tests -v` passed **47 tests**, including 12 adapter tests. The adapter cases exercise the request allowlist, label-to-ID mapping, abstentions, candidate limits, malformed and out-of-set replies, missing credentials, HTTP errors, timeouts, and redirect refusal. One case runs the real selection subprocess against SQLite with a mocked HTTP transport and checks eligibility and explicit reference fallback.
- `node --test tests/test_mode_isolation.mjs` passed **five tests**. Python compilation, JavaScript syntax checking, and `git diff --check` passed.
- Both optional Playwright checks stopped at Chromium launch because the environment blocked socket creation. The Python suite exercised the local HTTP endpoints.

All provider responses were simulated. The reference selector is still the default. This change made no paid inference calls and sent no personal history.

### Authenticated smoke test pending

With approval for one billable request, import `examples/demo.json` and `examples/demo-history.json` into a fresh temporary database. Use `--db` with the same path for both imports and the server. Supply `TYPESAFE_API_KEY` securely, start the [hosted selector](../README.md#optional-hosted-jev-selector) with reference fallback disabled, switch to demo mode, and request one pick. Check for a permitted selection or model abstention and confirm a successful request in TypeSafe’s usage console. This checks live authentication and response compatibility using only fictional data.
