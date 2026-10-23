# Changelog

Newest first, one entry per released version. Each entry carries the exact short (50 characters or fewer) and long (250 characters or fewer) commit text. Releases are built by pushing a tag `vMAJOR.MINOR.PATCH`.

## v0.4.1 - 2026-10-22
**Short:** Set 30s healthcheck start period
**Long:** Healthcheck start period is now 30 seconds in the image and compose. /healthz is unchanged and now fixed by tests: public, returns only status and version, checks only the local database. Image tag 0.4.1.

- P-3: the image HEALTHCHECK and the compose healthcheck both call `GET /healthz` on `127.0.0.1:$PORT` with a 30 second start period (was 20).
- `/healthz` itself did not change. It needs no login, returns only `{"status":"ok","version":"<image tag>"}`, and checks only the local database. Tests now fix this.

## v0.4.0 - 2026-10-22
**Short:** Adopt home server release flow, PWA, port 8044
**Long:** Tag-triggered build pushes mybadreligon/mealkit-manager X.Y.Z, X.Y, latest, then a GitHub release. Adds installable PWA with phone and desktop layouts, /healthz, tini, port 8044, deploy files and an Update field.

- P-1: a `vMAJOR.MINOR.PATCH` tag now builds and pushes `mybadreligon/mealkit-manager:X.Y.Z`, `X.Y` and `latest`, then creates the GitHub release. The old push-to-main image build is removed; `test.yml` runs the tests on pushes.
- P-1: default port is now 8044 (read from `PORT`, container port = host port). It was 3800 in v0.3 and 8000 before that: change the port mapping when updating.
- P-1: installable PWA (manifest, icons, service worker, offline page, update prompt, Install button), bottom navigation on phones and a sidebar on desktop, tables become cards on phones.
- P-1: `/healthz`, `tini` and graceful shutdown, container user 1000:100, schema version with a database copy before an upgrade, `/export.json`, `deploy/compose.yaml`, `deploy/.env.example`, `deploy/RELEASE.md`.
- P-2: `deploy/RELEASE.md` carries a fixed `Update: now` or `Update: later` line. It says `now` only when the build message was "build, push and update".
- Existing data upgrades in place (schema 2, no data changes). The image is larger than v0.2 because it includes Chromium.

## v0.3 - 2026-10-07
**Short:** Add account linking and automatic actions
**Long:** Add encrypted account linking, Playwright connectors for HelloFresh, Chef's Plate and Good Food, six-hourly status sync, and Auto/Ask skip, reactivate and cancel with safety checks and dry-run. Change port to 3800. Bump to 0.3.

- Linked accounts with encrypted logins, status sync, automatic skip, reactivate and cancel with safety checks, dry-run first. Port changed to 3800. Details in `docs/CHANGELOG-early.md` (CL-0005 to CL-0007).

## v0.2 - 2026-10-07
**Short:** Fix CI: add pytest.ini so tests import app
**Long:** Make pytest find the app package by adding pytest.ini with pythonpath and testpaths, fixing the GitHub Actions collection error. Bump VERSION to 0.2 so the failed v0.1 run is superseded by a clean release.

v0.1 was never published (its CI run failed at the test step). Its notes are in `docs/CHANGELOG-early.md` (CL-0001 to CL-0003).
