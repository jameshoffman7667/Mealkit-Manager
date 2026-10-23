# Meal Kit Subscription Manager

Plans continuous, discounted meal-kit delivery across several accounts and services (HelloFresh, Chef's Plate, Good Food). It tracks each account's discount window, decides which account delivers each week, tells you which weeks to skip, and tells you when to cancel so no account rolls onto full price.

The app is a **planner first**: you enter accounts, promo codes and offers, and it plans and reminds; you can do each skip, cancel and reactivate yourself and mark it done. From v0.3 you can also **link an account** (its login, stored encrypted) so the app reads the real status and weeks and, when you allow it, performs skips, reactivations and cancellations for you. See `docs/functional-spec.md`.

## Run it

```bash
docker run -d --name mealkit-manager -p 8044:8044 -v mealkit-data:/data \
  -e TZ=America/Toronto -e APP_PASSWORD=choose-a-password \
  mybadreligon/mealkit-manager:latest
```

Open `http://localhost:8044`. On the home server use `deploy/compose.yaml` (see `deploy/RELEASE.md`). The container runs as user 1000:100, so a data folder you mount must be owned by that user. To install the app on a phone or computer, open it through its `https://` address.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8044` | Port the portal listens on. Keep the container port equal to the host port. |
| `APP_PASSWORD` | empty (no login) | If set, the portal asks for HTTP Basic login: any username, this password. `/healthz` and the files needed to install the app stay open. |
| `TZ` | `America/Toronto` | Time zone used for "today" and week boundaries. |
| `HORIZON_WEEKS` | `12` | Default planning horizon (changeable in Settings). |
| `DATA_DIR` | `/data` | Folder for the SQLite database. Mount a volume here. |
| `SECRET_KEY` | empty | Required to link accounts: 16+ random characters. Encrypts the stored logins. Keep it; if it changes, enter the logins again. |
| `SYNC_HOURS` | `6` | Hours between background reads of linked accounts. `0` turns the background run off (the Sync buttons still work). |
| `AUTOMATION` | `on` | `off` stops all reading and changing of linked accounts. |
| `CONNECTOR_DEBUG` | off | `1` saves the text of pages the connectors read to `DATA_DIR/debug` (contains personal data) to help fix selectors. |

The portal has no CSRF protection and a single shared password. Run it on a home network or behind a reverse proxy with proper authentication, not on the open internet.

## Photo capture of promo codes

On a phone, open **Promo codes > Scan a code with the camera**. The file picker offers the camera (`capture="environment"`) or the gallery. The photo is read by Tesseract inside the container, the code, service, discount, weeks and expiry are proposed, and you confirm or edit before saving. The photo is processed in memory and never stored. This works over plain HTTP; only a live camera preview would need HTTPS, and v0.1 does not use one.

## Linking accounts and automatic actions (v0.3)

1. Set `SECRET_KEY` on the container, then open **Accounts** and use *Link this account* with the service login. The app signs in once to test it.
2. A new link is in **dry-run**: the app reads the account's real plan status and coming weeks, shows them on the week plan ("service: delivering/skipped"), and logs what it *would* do. Nothing is changed.
3. When the reads look right, tick *Make real changes* and choose a mode. **Auto** performs reactivate, skip and cancel at the planned time. **Ask first** waits for Approve on the Actions page. **Remind only** stays manual.
4. Every action is checked by reading the account again. If the check fails the action is not marked done, and after 3 failed attempts the app stops trying.
5. A cancel is refused if a payment problem is visible, or if a later box cannot be skipped.
6. If a site asks for a code or CAPTCHA the app stops and marks the account **Needs attention**. It never gets around these. Sign in on the site yourself, then press Sync now.

Important limits: the services have no public API, so the connectors drive their websites. The page paths and selectors in this release have **not been tested against the live sites** and will break when a site changes; fix them without a rebuild by putting overrides in `DATA_DIR/connectors.json`, for example `{"hellofresh": {"deliveries_path": "/my-account/deliveries", "card_sel": "[data-testid=card]"}}`. Automating an account may breach a service's terms. The image includes Chromium, so it is much larger than v0.2.

## How planning works

- Each account can have discount windows (a start week and a number of weeks). Applying a promo code to an account creates one.
- Per service you set the skip cut-off, how many days ahead to reactivate, and whether skipped weeks use up the window (default: no, the discount covers N delivered boxes). Check each service's current terms.
- Each week, one account delivers: the one whose discount runs out soonest. Every other active account is skipped. Cancelled accounts with a window are Waiting, and a reactivation is scheduled ahead of their first box.
- After an account's last discounted box a cancel is queued. An active account with no discount left is flagged At risk.
- Weeks with no discounted box show as gaps; the app never plans a full-price box unless you force one.
- The current week and weeks past the skip cut-off are locked. Past weeks are assumed to have followed the plan and use up window boxes. If reality differs, add an override on the week plan page.

## Develop and test

```bash
pip install -r requirements-dev.txt     # also needs the tesseract binary for real OCR
pytest -q
DATA_DIR=./data uvicorn app.main:app --reload
```

## Release process (GitHub to Docker Hub)

A release is a commit and a push to `main`. No tag is pushed by hand.

1. Requests are logged in `docs/pending-changes.md` and built only on a build message.
2. Change `VERSION` (MAJOR.MINOR.PATCH), add the newest entry to `CHANGELOG.md` with a short text (50 characters or fewer) and a long text (250 or fewer), and refresh `deploy/compose.yaml` (pinned to the new version), `deploy/.env.example` and `deploy/RELEASE.md`. Commit with the same short and long text and push `main`.
3. The push runs `.github/workflows/release.yml` because `VERSION` changed. It fails if the tag `vX.Y.Z` or a GitHub release for it already exists, or if the `CHANGELOG.md` entry is missing or too long. Otherwise it runs the tests, builds the image, pushes `mybadreligon/mealkit-manager:X.Y.Z`, `X.Y` and `latest`, and creates the GitHub release with `gh release create vX.Y.Z --target $GITHUB_SHA`, which also creates the tag. It needs the repository secrets `DOCKERHUB_USERNAME` (`mybadreligon`) and `DOCKERHUB_TOKEN`.
4. Pushes to `main` that do not change `VERSION` build nothing; `.github/workflows/test.yml` runs the tests.
5. Fallback: pushing a tag `vX.Y.Z` by hand runs the same workflow with the same checks. The two ways cannot release the same version twice.

Suggested commit messages for each release are in `CHANGELOG.md`; the history before v0.4.0 is in `docs/CHANGELOG-early.md`.
