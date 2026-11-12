# NoSpoilers

A local movie picker that leaves the story on the screen. Record movies you’ve seen, press **Pick for me**, and react after watching. Only title, year, optional runtime, and verified watch offers appear with a pick.

The local reference selector runs by default. An opt-in adapter for hosted TypeSafe Jev has been tested with mocked responses and still needs an authenticated smoke test.

## Run

Python 3.12 or later; validated with **Python 3.12.14** and its bundled SQLite. No runtime packages, accounts, keys, or build step are needed.

```sh
cd /workspace/nospoilers
python -m nospoilers serve
```

The browser interface is on local port **8000**. The server binds only to loopback. Open it locally, choose **Setup → Load fictional demo**, then add seen-title reactions in **Seen & rated**. Personal mode starts empty; demo data and optional synthetic history are separate. No real movies are spoiled in the fixtures.

Stop with Ctrl+C. Run the same command to restart. The default database is `.data/nospoilers.sqlite3`; use `python -m nospoilers --db /path/to/state.sqlite3 serve` for a different file. Protect and back up that file: it contains private narratives, taste data, notes, and reproducibility records. Local storage is not encrypted. This is a single-user local tool, not an Internet-facing hosted service.

**Another one** excludes the last offered movie in the current browser session and mode. It never changes a rating. **Reset this session’s skips** clears these exclusions. Closing a browser session starts a new session unless the browser restores its session cookie. Watched films stay excluded regardless of reaction; changing a reaction replaces the existing rating.

## Use your own catalog

Import authorized metadata, private features, and history server-side. You do not need to inspect unseen plots in the browser.

```sh
python -m nospoilers import /path/to/catalog.json
```

Start from `examples/import-template.json`. The full format, feature schema, availability policy, and exact response boundaries are in [docs/contracts.md](docs/contracts.md). Include seen titles and their features, even if they are absent from your unseen candidate list. Imports merge by namespaced ID and update current history without duplicates. They do not delete records. Back up before replacing records.

For bulk real metadata, obtain your own authorized TMDB read-access token and set **TMDB_READ_ACCESS_TOKEN** securely in your process environment. Do not place it in source or chat.

```sh
python -m nospoilers tmdb --pages 2 --ids 123,456
```

IDs above illustrate syntax, not recommendations. `--pages` accepts 0–10 discovery pages; `--ids` adds watched or other known TMDB IDs to the same feature store. The adapter preserves `tmdb:` IDs and IMDb mappings. Respect TMDB’s terms and attribution requirements (metadata from TMDB; availability from JustWatch via TMDB). API credentials, live network ingestion, and provider accuracy have **not** been verified in this environment. The adapter’s normalization and failure handling are tested with fictional payloads. Before selection, import precomputed profiles or enrich these records; TMDB plot text is stored privately and never sent to the viewing interface.

## Private preprocessing and integration

Precomputed features work without credentials. The reproducible fixture extraction path deliberately produces a fixed fixture profile; it is **not** story analysis and is limited to demo mode:

```sh
python -m nospoilers import examples/demo.json
python -m nospoilers extract --mode demo --fixture
```

This changes the demo features to an all-0.5 fixture. Reload the demo catalog to restore the designed profiles. Extraction caches use source-content SHA-256, extractor kind/version, and feature-schema version. A normal pick never calls an extractor.

For a separately configured model, supply a private subprocess adapter using JSON argv (no shell expansion), plus an immutable version covering model, prompt, and settings:

```sh
python -m nospoilers extract --mode real --command '["/absolute/path/to/extractor"]' --version my-model-prompt-v1
```

The executable must implement the exact contract in [docs/contracts.md](docs/contracts.md). A protocol test exercises a real subprocess; **actual model-backed extraction remains pending**. Imported source text is untrusted data. The application validates output and never displays extraction text, but the selected external executable and its handling of source data must be trusted.

## Optional hosted Jev selector

Only opt in if you agree to send the request data described below to TypeSafe and incur usage charges. Create a key in the TypeSafe console and inject `TYPESAFE_API_KEY` into the server process environment using a secret manager or a non-echoing prompt with shell tracing disabled. Keep the key out of command arguments, source files, logs, and chat. [TypeSafe API keys](https://console.typesafe.ai/settings/keys)

```sh
python -m nospoilers serve \
  --selector-command '["python","-m","nospoilers.jev"]' --candidate-limit 32
```

This configures the command selector for both catalog modes in that server process. Use the same Python interpreter for the server and the subprocess. Restart with `python -m nospoilers serve` to use the local reference selector. `--reference-fallback` explicitly enables the local picker on an integration error and records its use in diagnostics.

TypeSafe receives numeric candidate features under temporary labels, numeric mood targets, and rounded averages from liked and disliked profiles. Stable IDs, titles, plots, and individual history records stay local. Averages and features can still reveal tastes, particularly when the history is small. [Request and privacy details](docs/contracts.md#hosted-jev-adapter)

Use a `--candidate-limit` from 1 to 253. The command bridge shortlists eligible movies by ascending ID, which can affect recommendations. TypeSafe lists **$0.042 per million input tokens** with free output tokens. Actual cost depends on request size. [TypeSafe pricing](https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost)

The same command bridge accepts other executables using JSON argv and an explicit `--candidate-limit`. The **Setup** screen reports the configured backend and last-call timing. [Subprocess contract](docs/contracts.md#command-selector-protocol)

## Validate

```sh
python -m unittest discover -s tests -v
```

This runs real SQLite, HTTP, subprocess-contract, canary disclosure, eligibility, feedback, and persistence checks using fictional data. No third-party dependencies are needed. Browser acceptance is optional for ordinary development; it was also run for this delivery using **Playwright 1.62.0** with system Chromium:

```sh
# Optional: install the pinned browser-testing package in a virtual environment.
python -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
# System Chromium, or supply CHROMIUM_PATH for an existing executable.
PYTHONPATH=. .venv/bin/python tests/browser_check.py
```

The browser check starts and restarts its own isolated server and temporary database, tests the real flow and mobile layout, and writes screenshots to ignored `.data/artifacts/`. See [docs/verification.md](docs/verification.md) for measured results and limitations.
