# Change log

Newest first. Nothing is built until the instruction "build it and push it". Each entry has a short commit message (50 characters or fewer) and a long commit message (250 characters or fewer).

## CL-0007 | 2026-10-07 21:10 | v0.3 (built)

- Researched markswendsen-code/mcp-hellofresh and the mcpmarket listing for HelloFresh connection. Decision: use as a reference only, not a dependency.
- Why: Node/TypeScript (app is Python); one commit; guessed selectors with fallbacks that report success when a click was not confirmed; no 2FA/CAPTCHA handling; spoofed user agent; no cancel, reactivate or discount reading, which this app needs.
- v0.3 connector design: Python Playwright, one selector/flow file per service, verification re-read after every action, no stealth or bot-evasion, status read as page text. Chef's Plate is the same Hello Fresh Group platform so HelloFresh flows are the starting point, but must be confirmed against the live site. Good Food is separate and needs its own flow.
- Spec: LK-2 and LK-3 unchanged; connector design note added to 11.2.
- Short commit (44/50): `Base connectors on Playwright, dry-run first`
- Long commit (233/250): `Record research on mcp-hellofresh: use it as a reference only. Plan Python Playwright connectors with per-service selector files, no stealth, plain-text status reads, and live recon before enabling Auto. Applies to v0.3 linking work.`

## CL-0006 | 2026-10-07 20:45 | v0.3 (built)

- Add credentialed account linking: enter each account's login, stored encrypted with an operator-supplied key.
- Add automatic account activation (reactivate), skip and cancellation, performed by service connectors at the planned time for accounts set to Auto.
- Add automatic adding of plan status per week: a daily sync (and a sync before each cut-off) reads each linked account's upcoming weeks (delivering, skipped, paused) and records them as the actual state in the week plan, flagging any difference from the plan.
- Safety: new accounts start in dry-run; verification steps are never bypassed; cancel only after a safety check; every action is logged with evidence.
- Spec: added section 11.2 (requirements LK-1 to LK-8) with a v0.3 status table.
- Built as: `app/vault.py`, `app/connectors/` (Playwright), `app/automation.py`, `app/state.py`; new account columns migrate in place; Chromium added to the image; new `SECRET_KEY`, `SYNC_HOURS`, `AUTOMATION`, `CONNECTOR_DEBUG` settings.
- Not verified here: the connectors have never run against the real sites, and the Docker build and web tests could not run in this environment (no PyPI, no Docker). The first run on each account should stay in dry-run. Page paths and selectors are guesses until checked; override them in `connectors.json`.
- Short commit (41/50): `Add account linking and automatic actions`
- Pushed as one commit for v0.3 (CL-0005, CL-0006 and CL-0007 together), using this message.
- Long commit (227/250): `Add encrypted account linking, Playwright connectors for HelloFresh, Chef's Plate and Good Food, six-hourly status sync, and Auto/Ask skip, reactivate and cancel with safety checks and dry-run. Change port to 3800. Bump to 0.3.`

## CL-0005 | 2026-10-07 20:32 | v0.3 (built)

- Change the portal port from 8000 to 3800.
- Planned changes: Dockerfile `EXPOSE`, uvicorn `--port` and the health check URL; `docker-compose.yml` port mapping; README run examples and URL; VERSION bumped to 0.3.
- Anyone running v0.1 or v0.2 will need to change their port mapping to `3800:3800` when they move to v0.3.
- Spec: section 10.1 now states the port (3800 from v0.3).
- Short commit (26/50): `Change portal port to 3800`
- Long commit (180/250): `Switch the container and docker-compose from port 8000 to 3800: Dockerfile EXPOSE, uvicorn command and health check, compose port mapping, README run examples. Bump VERSION to 0.3.`

## CL-0004 | 2026-10-07 20:27 | v0.2 (built)

- Bug from the first GitHub Actions run (v0.1): `pytest -q` stopped at collection with `ModuleNotFoundError: No module named 'app'` in all three test files. Nothing was published to Docker Hub and no v0.1 git tag was created, because the run stopped at the test step.
- Cause: the repository root is not on Python's import path when `pytest` is run directly. The tests folder has no `__init__.py`, so pytest only adds `tests/` to the path.
- Fix: added `pytest.ini` with `pythonpath = .` and `testpaths = tests`.
- VERSION bumped to 0.2.
- Checked in this environment: scheduler and photo-parsing tests still pass. The web app tests and the Docker build still cannot run here (no PyPI access, no Docker daemon), so the GitHub Actions run is the check.
- Risk: `tests/test_app.py` has never run before this CI run, and CI installs newer FastAPI and Starlette than were available locally (FastAPI 0.142, Starlette 1.7). Once imports work, more failures may surface. They will be fixed in the same build.
- Short commit (42/50): `Fix CI: add pytest.ini so tests import app`
- Long commit (205/250): `Make pytest find the app package by adding pytest.ini with pythonpath and testpaths, fixing the GitHub Actions collection error. Bump VERSION to 0.2 so the failed v0.1 run is superseded by a clean release.`

## CL-0003 | 2026-10-07 19:43 | v0.1 (built)

- Docker image (Python 3.12 slim plus Tesseract) serving the FastAPI web portal on port 8000. Data in a /data volume, /health endpoint, optional APP_PASSWORD login.
- Pages: week plan calendar with overrides, action queue (mark done), accounts with discount windows, promo codes, settings (service rules, planning horizon, activity log).
- Scheduler: one delivery per week, soonest-expiring discount first, skip other live accounts, cancel after the last discounted box, planned reactivation, gap weeks, locked weeks, overrides.
- Promo codes: general or account-specific, win-back codes, apply a code to an account to create a discount window, expiry flagging.
- Photo capture: phone camera or gallery upload, Tesseract text recognition, proposed code, service, discount, weeks and expiry, editable confirmation, photo never stored.
- GitHub Actions workflow: runs tests, builds the image, pushes version and latest tags to Docker Hub, tags the commit. Fails if the version is already released. Docs-only pushes are skipped.
- VERSION file set to 0.1 and shown in the portal footer. Increment it on every build.
- Tests: 12 scheduler, 6 photo-text parsing, 9 web app.
- Checked in this environment: scheduler and parsing tests pass, a real Tesseract read of a generated image parsed correctly, all templates render, workflow and compose YAML parse.
- Not checked here (no PyPI access and no Docker daemon): the 9 web app tests and the Docker build. The CI workflow runs the tests before it publishes, so a failure stops the push to Docker Hub.
- Not in v0.1: account linking and automation, inbox parsing, 2FA, notifications, savings view, option to keep photos, suggested best code.
- Spec: added section 11 (implementation status). README added.

- Short commit (43/50): `Build v0.1: Docker portal, photo promo scan`
- Long commit (239/250): `Add v0.1 manual planner: FastAPI/SQLite web portal, week scheduler with skip/cancel/reactivate actions, promo codes and discount windows, phone photo OCR, Dockerfile, CI that tests and pushes to Docker Hub, tests. Docs-only pushes skip CI.`

## CL-0002 | 2026-10-07 19:23 | v0.1 (queued)

- Package as a Docker container serving a web portal.
- Add mobile photo capture of promo codes with visual recognition (OCR) and an editable confirmation step.
- Add GitHub repository and GitHub Actions workflow that pushes the image to Docker Hub.
- Start at v0.1 and increment the version on every build.
- Process: log changes as requested, build only on 'build it and push it', keep spec, change log and project files in one zip.
- Spec: added section 10 (delivery, packaging and release process).

- Short commit (40/50): `Log v0.1 requirements and build workflow`
- Long commit (197/250): `Record v0.1 scope: Dockerized web portal, mobile photo promo-code recognition, GitHub Actions push to Docker Hub, auto-incrementing version, and build-only-on-instruction rule. Add spec section 10.`

## CL-0001 | 2026-10-07 19:13 | Planning (docs only)

- Add functional spec for the meal kit subscription manager (HelloFresh, Chef's Plate, Good Food): account linking, general and account-specific promo codes, discount window tracking, week scheduler, auto-cancel, management views, notifications, data model, risks and phasing.

- Short commit (27/50): `Add initial functional spec`
- Long commit (196/250): `Add functional spec for meal kit subscription manager: account linking, promo codes, discount tracking, week scheduler, auto-cancel, management views, notifications, data model, risks and phasing.`
