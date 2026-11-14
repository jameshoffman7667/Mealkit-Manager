# Release v0.5.0
Image: mybadreligon/mealkit-manager:0.5.0   (built by the release workflow on the push to main that changed VERSION; also tagged 0.4 and latest)
Update: later
Short: Add Android app (TWA) APK for F-Droid repo
Long: Adds the Android app (TWA, ca.hoffmanhouse.mealkit): twa-manifest, assetlinks.json route, android release job that signs and attaches the APK, rebuild input. Scan errors now redirect. APK untested until confirmed. Image 0.5.0.
Release commit: the commit titled with the Short above on main (hash is in the release report)        Tag: created by the release workflow (gh release create --target); nobody pushes it
Type: minor (Android app, release workflow android job, assetlinks route; no data or env changes)
Port: 8044 (host = container; port register). Old host ports: 8000 (v0.1, v0.2), 3800 (v0.3), 3600 on the server.   Exception: none
Public hostname: mealkit.hoffmanhouse.ca (behind Cloudflare Access application "family apps")        Needs Caddy route: only if not yet created; upstream port 8044
New or changed env vars: PORT (default 8044). Unchanged: APP_PASSWORD, SECRET_KEY (names only; optional), HORIZON_WEEKS, SYNC_HOURS, AUTOMATION, TZ, DATA_DIR (image default /data)
Data: unchanged from 0.4.2 (no schema change). /data (SQLite), owned by 1000:100 as since 0.4.0.
Resources: idle about 80 to 150 MB RAM; up to about 500 MB while Chromium reads a linked account. Compose sets mem_limit 1g and cpus 1.5. Image is large (about 1 GB) because it includes Chromium.
Healthcheck: GET /healthz on $PORT -> 200 {"status":"ok","version":"0.5.0"}; no login, no private data, local database only. Image HEALTHCHECK and compose healthcheck use start period 30s (was 20s).
Verify after deploy:
  1. `curl -s http://127.0.0.1:8044/healthz` returns {"status":"ok","version":"0.5.0"} and the container shows healthy.
  2. Open the week plan: the existing accounts, promo codes and discount windows are still there, and the footer says v0.5.0.
  3. In the browser (https name): the install prompt or Settings > Install app appears, DevTools > Application shows the manifest and an activated service worker, and with the server stopped a reload shows the offline page.
  4. `curl -s https://mealkit.hoffmanhouse.ca/.well-known/assetlinks.json` (after the Cloudflare bypass) returns JSON naming ca.hoffmanhouse.mealkit and the fingerprint 72:C6:F8:1F:...:FB:8E, with no redirect and no login.
Android: package ca.hoffmanhouse.mealkit, versionCode 50000, APK mealkit-manager-0.5.0.apk on the GitHub release; first F-Droid APK UNTESTED until James confirms it on his phone. Needs the four ANDROID_* GitHub secrets (set) and /.well-known/assetlinks.json served (this image serves it).
PWA: installable on phone and desktop at https://<hostname> (manifest, icons, service worker, offline page, update prompt, Install button). Layouts checked at 390x844, 768x1024, 1440x900 and 320 wide on the rendered pages, see the release report. Lighthouse: not run. Cloudflare Access bypass needed for /manifest.webmanifest, /sw.js, /icons/*, /static/*, /offline, /healthz and /.well-known/assetlinks.json (the last is new; the rest are already allowed).
Docker build: not run locally (no Docker daemon in the authoring session); it runs in the release workflow. Android build: runs only in the release workflow (android job); not seen before the push. Tests: scheduler, automation, parsing, PWA and Android file tests ran locally; the web page tests (including the assetlinks route) run in the test job.
Rollback: the previous published image is 0.4.2 (same data, same env); change the image tag back and restore the pre-update data copy if needed. The APK is separate: do not delete the v0.5.0 release asset once the F-Droid updater may have fetched it.
Known issues: account connectors have not been tested against the live HelloFresh, Chef's Plate or Good Food sites; keep accounts in dry-run until the sync results look right. The service worker and install flow were checked on a local test server, not behind Cloudflare.
Backup tier: small/critical (include in Tier 1); SQLite needs the container stopped during a copy, or use Settings > Download all data (JSON, without logins)
