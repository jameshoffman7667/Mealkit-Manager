# Pending changes log: mealkit-manager

Requests are logged here and built only when James sends a build message (for example "build P-1").

## Pending

### P-1 - Switch to the standard home server release flow
Requested: 2026-10-22 (James: "switch this app to the standard release flow in the home server app spec ... tell me the version number I should use for the first tag")
Type: minor (release pipeline and packaging change, no change to what the app does)        Status: Pending
Scope when built: tag `vMAJOR.MINOR.PATCH` triggers the workflow, which builds and pushes `mybadreligon/mealkit-manager:X.Y.Z`, `X.Y` and `latest` and creates the GitHub release as its last step; replace the push-to-main workflow; VERSION becomes three-part; add CHANGELOG short/long checks; add `deploy/RELEASE.md`, `deploy/compose.yaml`, `deploy/.env.example`; move the Docker Hub image from the old secrets-based name to `mybadreligon`.
Decisions (James, 2026-10-22):
- First tag v0.4.0 (v0.3 is already tagged and published).
- Port: 8044 is the default (`PORT` env, container port = host port 8044). Replaces 3800.
- Include in this release: installable PWA (manifest, service worker, icons, wide and narrow screenshots, offline page, update prompt, install button), phone and desktop layouts, `/healthz`, SIGTERM handling with `tini`.
- Docker Hub image name `mybadreligon/mealkit-manager` (lowercase, hard-coded in the workflow).
Notes: the build runs only after a build message.

### P-2 - Add a fixed "Update:" field to deploy/RELEASE.md
Requested: 2026-10-22 (James: "In deploy/RELEASE.md, add a fixed field Update: now or Update: later. Write Update: now only when I say 'build, push and update' for this release; otherwise write Update: later.")
Type: patch (release note format)        Status: Pending
Notes / questions:
- Rule as I understand it: `Update: now` only if the build message for that release is "build, push and update"; any other build message (for example "build P-1", "build it", "release it") gives `Update: later`. Decided per release, not remembered from the previous one. Applies to every release of this app, starting with the one that builds this entry.
- Planned for the same release as P-1, so v0.4.0's RELEASE.md carries the field. The field sits on its own line near the top, after the Image line.
- Open: should `Update: now` also change anything else in the report (for example mark the Claude Code prompt as ready to run), or is it only a label in RELEASE.md? I will treat it as a label only unless you say otherwise.

## Done

(none yet)
