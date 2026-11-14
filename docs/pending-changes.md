# Pending changes log: mealkit-manager

Requests are logged here and built only when James sends a build message (for example "build P-1").

## Pending

### P-5 - Fix deploy notes from the first server update
Requested: 2026-10-22 (James attached Claude Code's update plan with its feedback "for the mealkit chat")
Type: patch (deploy files and notes only; no app change)        Status: Pending
From the plan (facts reported by Claude Code):
- `deploy/RELEASE.md` says "Public hostname: TBD, Claude Code to confirm the existing hostname". There is none today: the app is LAN-only (port 3600) with no Caddy route and no Cloudflare hostname. Say so, and list what installing it needs (new https hostname, Caddy route, tunnel hostname to http://caddy:80, Access bypass paths /manifest.webmanifest, /sw.js, /icons/*, /static/*, /offline, /healthz). Also "Needs Caddy route: yes, upstream port changes to 8044" should read "new route needed".
- Verify command: vm101 has `wget` but not `curl`; the host check is `wget -qO- http://127.0.0.1:8044/healthz` (the container healthcheck still uses `curl`, which the image has).
- `deploy/compose.yaml` differs from the server stack (service name `mealkit`, not `mealkit-manager`; empty APP_PASSWORD; no PORT, SYNC_HOURS, AUTOMATION, user, healthcheck or limits). Bring the reference file in line with what the server will run after the update (service name `mealkit`).
- Rollback note: v0.3 runs as uid 10001, so a rollback means restoring the pre-update data copy (it keeps the old owner). Replace the "chown back" wording.
- Add the root step to RELEASE.md: after the data copy, `sudo chown -R 1000:100 <data folder>` before the first start.
Notes / questions:
- Decision for the server update (James): start with AUTOMATION=off or on? Both are safe until SECRET_KEY is set and an account is linked and live; nothing else in the app reads it. Not a code change.
- Should the compose default for AUTOMATION change to `off` in deploy/compose.yaml? (my suggestion: yes, until the connectors are checked on the live sites)

### P-7 - Account logins fail on HelloFresh and Chef's Plate
Requested: 2026-11-14 (James: "The logins aren't working for HelloFresh, and Chef's Plate says it can't find a login page")
Type: patch (connector fix; may become minor if a new sign-in flow must be built)        Status: Pending (blocked on details)
Notes / questions:
- Expected from the code: the site profiles in `app/connectors/profiles.py` (login path `/login`, email/password/submit selectors) are unverified guesses; the connectors have never run against the live sites. Chef's Plate's message matches "Could not find the sign-in form at <base>/login" (wrong login path, or the form is not an email + password pair on that page). HelloFresh's wording is not known yet.
- Likely causes: wrong login URL, the sign-in being a two-step form (email first, then password) or opening in a pop-up, a cookie banner covering the form, or a bot check (CAPTCHA) blocking the headless browser. AL-7 says the app never tries to bypass a CAPTCHA or identity check.
- Needed from James: (1) the exact red message shown for each account (Accounts page, link state or the activity log on Settings); (2) in a normal browser, the address of the sign-in page for each service and whether it asks for email and password together or in two steps, and whether a pop-up, cookie banner or "are you human" check appears; (3) a screenshot of each sign-in page if easy.
- Optional for diagnosis: set DEBUG_CAPTURE on the server for one run (saves the text of each page the connector reads to /data/debug; it contains personal data, so James reviews it before sharing anything).
- Interim workaround with no code change: the login path and selectors can be overridden per service in /data/connectors.json once the real values are known (Claude Code can place it).
- Accounts stay in dry-run, so nothing is changed on the services while this is open.
- Findings 2026-11-14 (James's phone screenshots): Chef's Plate error is "Could not find the sign-in form at https://www.chefsplate.com/login"; HelloFresh error is "The service did not accept the login. Check the email and password." Both addresses are right: chefsplate.com/login and hellofresh.ca/login each show a single page with email, password and a Log in button. So the path is not the problem; the form fields are probably not matched by the guessed selectors (`input[type="email"], input[name="email"], input[id="email"]`; submit `button[type="submit"]`), or the page is not ready when the connector fills it (single-page sites), or a bot check blocks the headless browser.
- HelloFresh specifics: the page also has "Keep me signed in", "Log in without password" (an email link, which would also be a button), Google and Facebook sign-in. The submit selector may hit the wrong button. "Did not accept" also appears whenever the page still shows a password box on a URL containing "login" after the click, so it does not prove the password is wrong.
- Open question for James: do both accounts have a password, or do you normally sign in with Google, Facebook or the emailed link? Accounts created through Google or Facebook have no password to store, and an emailed-link or code sign-in cannot be automated (AL-7).
- Next step needing no code change: Claude Code runs a read-only check from inside the container that opens each login page with the app's Playwright browser, with no credentials, and prints the form fields and buttons it sees (names, ids, types, labels), whether it is blocked, and a screenshot. That gives the exact selectors for connectors.json or for a patch.

## Done

### P-1 - Switch to the standard home server release flow
Requested: 2026-10-22 (James: "switch this app to the standard release flow in the home server app spec ... tell me the version number I should use for the first tag")
Type: minor (release pipeline and packaging change, no change to what the app does)        Status: Built in v0.4.0
Scope when built: tag `vMAJOR.MINOR.PATCH` triggers the workflow, which builds and pushes `mybadreligon/mealkit-manager:X.Y.Z`, `X.Y` and `latest` and creates the GitHub release as its last step; replace the push-to-main workflow; VERSION becomes three-part; add CHANGELOG short/long checks; add `deploy/RELEASE.md`, `deploy/compose.yaml`, `deploy/.env.example`; move the Docker Hub image from the old secrets-based name to `mybadreligon`.
Decisions (James, 2026-10-22):
- First tag v0.4.0 (v0.3 is already tagged and published).
- Port: 8044 is the default (`PORT` env, container port = host port 8044). Replaces 3800.
- Include in this release: installable PWA (manifest, service worker, icons, wide and narrow screenshots, offline page, update prompt, install button), phone and desktop layouts, `/healthz`, SIGTERM handling with `tini`.
- Docker Hub image name `mybadreligon/mealkit-manager` (lowercase, hard-coded in the workflow).
Notes: the build runs only after a build message.

### P-2 - Add a fixed "Update:" field to deploy/RELEASE.md
Requested: 2026-10-22 (James: "In deploy/RELEASE.md, add a fixed field Update: now or Update: later. Write Update: now only when I say 'build, push and update' for this release; otherwise write Update: later.")
Type: patch (release note format)        Status: Built in v0.4.0
Notes / questions:
- Rule as I understand it: `Update: now` only if the build message for that release is "build, push and update"; any other build message (for example "build P-1", "build it", "release it") gives `Update: later`. Decided per release, not remembered from the previous one. Applies to every release of this app, starting with the one that builds this entry.
- Planned for the same release as P-1, so v0.4.0's RELEASE.md carries the field. The field sits on its own line near the top, after the Image line.
- Open: should `Update: now` also change anything else in the report (for example mark the Claude Code prompt as ready to run), or is it only a label in RELEASE.md? I will treat it as a label only unless you say otherwise.

### P-3 - /healthz contract and 30 second start period
Requested: 2026-10-22 (James: "Make sure the app answers GET /healthz on $PORT with {"status":"ok","version":"<same as the image tag>"}, no login, no private data, and no checks of outside services. Add a matching HEALTHCHECK to the image and the compose file, with a 30 second start period.")
Type: patch (health check setting; the endpoint already behaves this way)        Status: Built in v0.4.1
Notes / questions:
- Already true in v0.4.0: GET /healthz on $PORT needs no login, returns only status and version (version comes from the VERSION file, which equals the image tag), and checks only the local database, never an outside service. The image HEALTHCHECK and compose healthcheck both call it on 127.0.0.1:$PORT.
- To change: start period 20s -> 30s in the Dockerfile and deploy/compose.yaml; add tests that fix the contract (exact JSON keys, no auth, version equals VERSION, start period 30s in both files).
- Decision: kept. If the database cannot be read, /healthz returns 503 and the container shows unhealthy.
- Working rule noted (not a build item): no zip delivery from now on; releases are pushed to GitHub only.

### P-4 - Release without a tag push
Requested: 2026-10-22 (James: "If the tag pushes are failing, change the release workflow so it never needs a tag push ... build and push this change")
Type: patch (release pipeline)        Status: Built in v0.4.2
Notes: trigger is a push to main that changes `VERSION` (this app has no package.json); `gh release create vX.Y.Z --target $GITHUB_SHA` creates the tag; the `v*.*.*` tag trigger stays as a manual fallback; both share a concurrency group per version and refuse an existing tag or release.

### P-6 - Android app (TWA) published to the F-Droid repo
Requested: 2026-11-13 (James: build message with spec v1.11 section 15, android-template-bundle.md)
Type: minor        Status: Built in v0.5.0
Notes: package ca.hoffmanhouse.mealkit, host mealkit.hoffmanhouse.ca, alias mealkit. Web Push is not used, so `enableNotifications` is false. assetlinks.json lives in `app/static/` and is served at `/.well-known/assetlinks.json`. Back-button audit result is in docs/functional-spec.md section 10.10. First APK untested until James confirms it on his phone; the F-Droid listing waits for that.

