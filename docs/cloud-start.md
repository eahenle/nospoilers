# Cloud startup instructions

Use the existing `/workspace/nospoilers` checkout. Each cloud task is already isolated; do not create a Git worktree unless explicitly requested. Preserve user files and `.data/nospoilers.sqlite3`.

Python 3.12+ is required (validated 3.12.14, SQLite 3.53.1). There are no third-party runtime packages or build/install steps. No credentials are required for the demo/reference workflow.

1. Work in `/workspace/nospoilers`; read `README.md` and `docs/contracts.md`.
2. Run `python -m unittest discover -s tests -v`. Tests own temporary databases and do not modify the real profile.
3. Start `python -m nospoilers serve` in a persistent execution session. It binds to loopback port 8000. Processes must restart in new tasks; do not assume snapshot restoration preserves a running server. If the port is occupied, identify the process before starting a duplicate or stopping anything.
4. Make local GET requests to `/api/state?mode=real` and `/` on port 8000. Expect HTTP 200, profile counts/constraints and the NoSpoilers interface respectively. Do not publish a loopback preview link during onboarding.
5. Use **Setup → Load fictional demo** to try the app without credentials. This loads 12 invented movies without ratings into a separate demo catalog. Synthetic demo history is a separate explicit action. Never add synthetic reactions to the personal profile.
6. SQLite state is at `.data/nospoilers.sqlite3`. Keep it private. Never serve the database, fixtures, plot text, private features or selector rationale. Authorized real imports use `python -m nospoilers import /path/to/catalog.json`.

Optional browser acceptance: `PYTHONPATH=. python tests/browser_check.py` uses the installed Playwright 1.62.0 and `/usr/bin/chromium`, starts/restarts its own server with a temporary database, and writes ignored screenshots in `.data/artifacts/`. If the optional tooling is absent, `requirements-browser.txt` pins Playwright and `CHROMIUM_PATH` selects an installed Chromium. Browser tooling is not needed to run the application.

Reference selector working; Jev integration pending. No Jev implementation/checkpoint/SDK/API was supplied. Real model extraction requires a separately configured executable. TMDB ingestion requires the optional `TMDB_READ_ACCESS_TOKEN` and authorized source access. Neither integration is needed for the local demo, and neither was verified live. Fixture extraction and subprocess contracts were verified.

## Draft persistence

The onboarding configuration API returned `INVALID_ARGUMENT` for both save and draft reads in this chat. Runtime status remained healthy and identified the selected environment, but no draft persistence was confirmed. These instructions are retained here for environment settings. The application was validated in the current instance; publication and restoration in a new task are unverified.
