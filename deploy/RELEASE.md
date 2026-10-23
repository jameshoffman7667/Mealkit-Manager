# Release v0.4.2
Image: mybadreligon/mealkit-manager:0.4.2   (built by the release workflow on the push to main that changed VERSION; also tagged 0.4 and latest)
Update: later
Short: Release on VERSION push, no tag push needed
Long: Pushing a changed VERSION to main now runs the release: checks, tests, image X.Y.Z, X.Y and latest, then gh release create makes the tag. Tag trigger stays as manual fallback. Guards stop double releases. Image tag 0.4.2.
Release commit: the commit titled with the Short above on main (hash is in the release report)        Tag: created by the release workflow (gh release create --target); nobody pushes it
Type: patch (release workflow change; the app itself is as v0.4.1)
Port: 8044 (host = container; port register). Old host ports: 8000 (v0.1, v0.2), 3800 (v0.3), 3600 on the server.   Exception: none
Public hostname: TBD, Claude Code to confirm the existing hostname (an https name is needed to install the app)        Needs Caddy route: yes, upstream port changes to 8044
New or changed env vars: PORT (default 8044). Unchanged: APP_PASSWORD, SECRET_KEY (names only; optional), HORIZON_WEEKS, SYNC_HOURS, AUTOMATION, TZ, DATA_DIR (image default /data)
Data: unchanged from 0.4.0. /data (SQLite). The image now runs as 1000:100 (v0.1 to v0.3 ran as uid 10001), so the data folder must be owned 1000:100: stop the old container, copy the old volume contents into FAST_STORAGE/mealkit-manager (or chown the existing folder) with `chown -R 1000:100`, keep a backup first. Migration: schema 1 or 2 to 2, additive only; the app writes /data/backups/pre-migrate-*.db before upgrading an older database. Reversible: the v0.3 image still starts on the migrated data.
Resources: idle about 80 to 150 MB RAM; up to about 500 MB while Chromium reads a linked account. Compose sets mem_limit 1g and cpus 1.5. Image is large (about 1 GB) because it includes Chromium.
Healthcheck: GET /healthz on $PORT -> 200 {"status":"ok","version":"0.4.2"}; no login, no private data, local database only. Image HEALTHCHECK and compose healthcheck use start period 30s (was 20s).
Verify after deploy:
  1. `curl -s http://127.0.0.1:8044/healthz` returns {"status":"ok","version":"0.4.2"} and the container shows healthy.
  2. Open the week plan: the existing accounts, promo codes and discount windows are still there, and the footer says v0.4.2.
  3. In the browser (https name): the install prompt or Settings > Install app appears, DevTools > Application shows the manifest and an activated service worker, and with the server stopped a reload shows the offline page.
PWA: installable on phone and desktop at https://<hostname> (manifest, icons, service worker, offline page, update prompt, Install button). Layouts checked at 390x844, 768x1024, 1440x900 and 320 wide on the rendered pages, see the release report. Lighthouse: not run. Cloudflare Access bypass needed for /manifest.webmanifest, /sw.js, /icons/*, /static/*, /offline and /healthz.
Docker build: not run locally (no Docker daemon in the authoring session); the first build is the tag workflow. Tests: scheduler, automation, parsing and PWA file tests ran locally with a stand-in runner; the web page tests run in the test workflow.
Rollback: the previous published image is 0.3 (v0.4.0 and v0.4.1 were never published). It ran as uid 10001, so chown the data folder back to that owner or restore the pre-update copy; schema changes are additive, so 0.3 starts on migrated data.
Known issues: account connectors have not been tested against the live HelloFresh, Chef's Plate or Good Food sites; keep accounts in dry-run until the sync results look right. The service worker and install flow were checked on a local test server, not behind Cloudflare.
Backup tier: small/critical (include in Tier 1); SQLite needs the container stopped during a copy, or use Settings > Download all data (JSON, without logins)
