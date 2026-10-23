# Pending changes log: mealkit-manager

Requests are logged here and built only when James sends a build message (for example "build P-1").

## Pending

### P-1 - Switch to the standard home server release flow
Requested: 2026-10-22 (James: "switch this app to the standard release flow in the home server app spec ... tell me the version number I should use for the first tag")
Type: minor (release pipeline and packaging change, no change to what the app does)        Status: Pending
Scope when built: tag `vMAJOR.MINOR.PATCH` triggers the workflow, which builds and pushes `mybadreligon/mealkit-manager:X.Y.Z`, `X.Y` and `latest` and creates the GitHub release as its last step; replace the push-to-main workflow; VERSION becomes three-part; add CHANGELOG short/long checks; add `deploy/RELEASE.md`, `deploy/compose.yaml`, `deploy/.env.example`; move the Docker Hub image from the old secrets-based name to `mybadreligon`.
Notes / questions:
- Proposed first tag: v0.4.0 (v0.3 is already tagged and published, so 0.3.0 would clash in meaning; a minor bump because the packaging changes).
- The repo is named `Mealkit-Manager` (capital letters) but Docker Hub names must be lowercase, so the workflow will hard-code `mybadreligon/mealkit-manager`.
- Port: the app listens on 3800 now. The server spec lists mealkit-manager as 8044 in the port register. Should v0.4.0 keep 3800 as the default and let `PORT` set the host port (my plan), or default to 8044? The app currently has the port fixed in the Dockerfile; the standard flow needs it read from `PORT`.
- The spec also asks for a PWA (manifest, service worker, icons, screenshots, install prompt), `/healthz`, SIGTERM handling and `tini`. The app has none of these yet. Include them in this release, or release the pipeline first and log the PWA as its own entry?

## Done

(none yet)
