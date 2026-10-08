# Change log

Newest first. Nothing is built until the instruction "build it and push it". Each entry has a short commit message (50 characters or fewer) and a long commit message (250 characters or fewer).

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
