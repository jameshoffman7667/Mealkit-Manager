# Release v0.5.1
Image: mybadreligon/mealkit-manager:0.5.1   (built by the release workflow on the push to main that changed VERSION; also tagged 0.5 and latest)
Update: now
Short: Fix HelloFresh and Chef's Plate sign-in
Long: Sign-in now uses the real login fields read from both sites, presses Enter if the button is not found, waits up to 12 s for the page to move on, and shows the site's own error text. Plan and delivery pages are still unverified.
Release commit: see the release report (the push of this version to main)        Actions run: see the release report        Tag: created by the release workflow (gh release create --target); nobody pushes it
Type: patch (connector sign-in fix, P-7; no data, env or compose changes besides the image tag)
Port: 8044 (host = container; port register). Old host ports: 8000 (v0.1, v0.2), 3800 (v0.3), 3600 on the server.   Exception: none
Public hostname: mealkit.hoffmanhouse.ca (behind Cloudflare Access application "family apps")        Needs Caddy route: only if not yet created; upstream port 8044
New or changed env vars: PORT (default 8044). Unchanged: APP_PASSWORD, SECRET_KEY (names only; optional), HORIZON_WEEKS, SYNC_HOURS, AUTOMATION, TZ, DATA_DIR (image default /data)
Data: unchanged from 0.4.2 (no schema change). /data (SQLite), owned by 1000:100 as since 0.4.0.
Resources: idle about 80 to 150 MB RAM; up to about 500 MB while Chromium reads a linked account. Compose sets mem_limit 1g and cpus 1.5. Image is large (about 1 GB) because it includes Chromium.
Healthcheck: GET /healthz on $PORT -> 200 {"status":"ok","version":"0.5.1"}; no login, no private data, local database only. Image HEALTHCHECK and compose healthcheck use start period 30s (was 20s).
Verify after deploy:
  1. `curl -s http://127.0.0.1:8044/healthz` returns {"status":"ok","version":"0.5.1"} and the container shows healthy.
  2. Open the week plan: the existing accounts, promo codes and discount windows are still there, and the footer says v0.5.1.
  3. In the browser (https name): the install prompt or Settings > Install app appears, DevTools > Application shows the manifest and an activated service worker, and with the server stopped a reload shows the offline page.
  4. `curl -s https://mealkit.hoffmanhouse.ca/.well-known/assetlinks.json` returns JSON naming ca.hoffmanhouse.mealkit and the fingerprint 72:C6:F8:1F:...:FB:8E, with no redirect and no login.
  5. Accounts page: press Save and test sign-in on a HelloFresh or Chef's Plate account (still in dry-run). It should say linked, or show the site's own error text.
AI: none (OCR of promo photos is local Tesseract; no model or outside AI call); registry rows added/changed/removed: none
Android: package ca.hoffmanhouse.mealkit, versionCode 50001, asset mealkit-manager-0.5.1.apk on the GitHub release; android job result: see the release report; assetlinks.json served: yes (verified by Claude Code 2026-11-14, bypass applied); Cloudflare Access bypass paths done: yes; first APK UNTESTED until James confirms it on his phone; F-Droid apps.txt: waiting for phone confirmation
PWA: installable on phone and desktop at https://<hostname> (manifest, icons, service worker, offline page, update prompt, Install button). Layouts checked at 390x844, 768x1024, 1440x900 and 320 wide on the rendered pages, see the release report. Lighthouse: not run. Cloudflare Access bypass needed for /manifest.webmanifest, /sw.js, /icons/*, /static/*, /offline, /healthz and /.well-known/assetlinks.json (the last is new; the rest are already allowed).
Docker build: not run locally (no Docker daemon in the authoring session); it runs in the release workflow. Tests: 72 passed, 1 skipped locally (including the new sign-in tests against a fake page); the web page tests run in the test job. The sign-in was not run against the live sites.
Rollback: the previous published image is 0.5.0 (same data and env); change the tag back, or restore the pre-update data copy if needed. Schema is unchanged.
Known issues: HelloFresh and Chef's Plate sign-in selectors now come from the live login pages, but the sign-in itself is untested with real credentials, and the plan and delivery pages are still unverified; Good Food not probed. Keep accounts in dry-run until a test sign-in and a sync look right.
Backup tier: small/critical (include in Tier 1); SQLite needs the container stopped during a copy, or use Settings > Download all data (JSON, without logins)
