# Meal Kit Subscription Manager

Plans continuous, discounted meal-kit delivery across several accounts and services (HelloFresh, Chef's Plate, Good Food). It tracks each account's discount window, decides which account delivers each week, tells you which weeks to skip, and tells you when to cancel so no account rolls onto full price.

Version 0.1 is a **manual planner**: you enter accounts, promo codes and offers, the app plans and reminds, and you perform each skip, cancel and reactivate on the service's own site, then mark it done. Account linking and automation are later phases (see `docs/FUNCTIONAL_SPEC.md`).

## Run it

```bash
docker run -d --name mealkit -p 8000:8000 -v mealkit-data:/data \
  -e TZ=America/Toronto -e APP_PASSWORD=choose-a-password \
  YOUR_DOCKERHUB_USER/mealkit-manager:latest
```

Open `http://localhost:8000`. Or use `docker compose up -d` with the included `docker-compose.yml`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PASSWORD` | empty (no login) | If set, the portal asks for HTTP Basic login: any username, this password. `/health` stays open. |
| `TZ` | `America/Toronto` | Time zone used for "today" and week boundaries. |
| `HORIZON_WEEKS` | `12` | Default planning horizon (changeable in Settings). |
| `DATA_DIR` | `/data` | Folder for the SQLite database. Mount a volume here. |

The portal has no CSRF protection and a single shared password. Run it on a home network or behind a reverse proxy with proper authentication, not on the open internet.

## Photo capture of promo codes

On a phone, open **Promo codes > Scan a code with the camera**. The file picker offers the camera (`capture="environment"`) or the gallery. The photo is read by Tesseract inside the container, the code, service, discount, weeks and expiry are proposed, and you confirm or edit before saving. The photo is processed in memory and never stored. This works over plain HTTP; only a live camera preview would need HTTPS, and v0.1 does not use one.

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

1. Create the GitHub repository and push this project to `main`.
2. In the repository settings add secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (a Docker Hub access token with write access).
3. Every build increments the number in the `VERSION` file (0.1, 0.2, 0.3, ...).
4. Pushing to `main` runs `.github/workflows/docker-publish.yml`: it runs the tests, builds the image, pushes `USER/mealkit-manager:<version>` and `:latest` to Docker Hub, and tags the commit `v<version>`. It fails if that version tag already exists, so a forgotten version bump is caught. Pushes that only change `docs/` or `*.md` files do not trigger a release.

Suggested commit messages for each build are in `CHANGELOG.md`.
