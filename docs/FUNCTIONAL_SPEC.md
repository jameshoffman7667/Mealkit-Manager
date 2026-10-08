# Meal Kit Subscription Manager: Functional Specification

Oct 7, 2026

The app keeps one household supplied with discounted meal kits every week by rotating across services and accounts, using each company's win-back offer (a multi-week discount for returning after cancelling) and cancelling each account the moment its discount ends.

## 1. Overview and goals

**Problem.** HelloFresh, Chef's Plate and Good Food all offer returning customers a discount lasting a fixed number of weeks. Capturing those offers across several accounts means tracking when each offer starts and ends, which weeks each account delivers, and when to cancel. Done by hand across calendars and emails, it is error-prone, and a missed cancellation means a full-price box.

**Strategy the app automates.**

1. Hold several accounts per service, each in a different state (active, discounted, cancelled and waiting for a win-back offer).
2. Reactivate an account when it has a win-back offer, and record the offer's discounted weeks.
3. Assign each calendar week to exactly one discounted delivery, and skip the account's other weeks.
4. Cancel the account once its last discounted week has been delivered or skipped past, so it never rolls onto full price.
5. Move on to the next account with an offer so there is no gap in delivery.

**Goals.**

- Every delivery week in the planning horizon is covered by exactly one discounted box, or is deliberately empty.
- No account is ever charged a full-price box that the user did not choose.
- The user can see, per week, which account and service delivers, what is skipped, and what is inactive.

**Success metrics.**

| Metric | Target |
| --- | --- |
| Weeks in horizon covered by a discounted delivery | at least 90% when enough offers exist |
| Full-price boxes charged without user approval | 0 |
| Accounts cancelled by the app within 24 h of their last discounted week | at least 99% |
| Duplicate deliveries in one week (two active subscriptions both shipping) | 0 |

## 2. Scope

**In scope (v1).** Three services: HelloFresh, Chef's Plate and Good Food, for personal household use in Canada. Multiple accounts per service. Account linking, promo code library, discount tracking, a week-by-week scheduler, skip and cancel automation, notifications, and a management calendar.

**Out of scope (v1).** Other meal-kit or grocery services, recipe or menu selection beyond a default "auto-skip or keep current selection" choice, payment method management, sharing accounts between households, and any marketplace for buying or selling accounts or codes.

**Persona.** One primary user (the household planner) who owns several accounts, each registered with a different email and often a different delivery address or payment method, and who wants hands-off, predictable weekly delivery at the lowest cost.

**Service notes to verify during discovery.** As far as I know, Chef's Plate is owned by HelloFresh and Good Food is a separate Canadian company, so offer rules, skip cut-offs and fraud checks differ by service. Each service gets its own rule profile (see section 7) rather than assumptions baked into the core logic.

## 3. Key concepts

| Term | Definition |
| --- | --- |
| Service | A meal-kit company (HelloFresh, Chef's Plate, Good Food). |
| Account | One login on a service. Has a status, delivery address and payment method. |
| Promo code | A code with a service, a discount, an optional account restriction and an expiry. Scope is **general** (any account on that service) or **account-specific**. |
| Win-back offer | A discount that applies for N weeks after an account returns from cancellation. Usually delivered by email or shown at reactivation. |
| Discount window | The N discounted weeks granted by an offer or code, with a start date and a count of weeks remaining. |
| Delivery week | A calendar week (Monday to Sunday, user time zone) in which one box can arrive. |
| Week assignment | The decision for one delivery week: which account and service delivers, or none. |

**Week states** (per account, per delivery week):

| State | Meaning |
| --- | --- |
| Delivering | This account ships a discounted box this week. Consumes one discounted week. |
| Skipped | Account is active but skipped this week, either to avoid a duplicate delivery or because another account is delivering. Does not consume a discounted week unless the service counts skips against the window (a per-service rule). |
| Inactive | Account is cancelled or paused. No charges. |
| Waiting | Account is cancelled and has a known offer that has not started yet. |
| At risk | Account would ship at full price (no discount remaining) and needs a decision or a cancellation. |

## 4. Account linking and promo codes

### 4.1 Account linking

| ID | Requirement |
| --- | --- |
| AL-1 | The user can add an account to a service by one of two methods: **Linked** (app signs in on the user's behalf and syncs status) or **Manual** (user records status and dates by hand). |
| AL-2 | Linked accounts authenticate through the best method available per service (see section 7). Credentials are never shown again after entry and are stored encrypted. |
| AL-3 | On link, the app imports: subscription status, plan size, delivery day, delivery address (masked), next delivery date, skipped weeks, and any visible discount or credit. |
| AL-4 | Each account has a nickname, a service, an email, an optional note, and a health state: Connected, Needs re-login, Sync failing, Manual. |
| AL-5 | The user can pause automation on a single account, or on all accounts, without unlinking. |
| AL-6 | Unlinking deletes stored credentials and tokens immediately and keeps the account's history unless the user deletes it. |
| AL-7 | If a login needs a one-time code, CAPTCHA or identity check, the app asks the user to complete it and never tries to bypass it. |

### 4.2 Promo codes

| ID | Requirement |
| --- | --- |
| PC-1 | The user can add a promo code with: service, code text, description, discount (percent or fixed amount per box), number of discounted weeks, applicable plans, expiry date, and source (email, friend, ad). |
| PC-2 | Scope is **General** (any account on that service) or **Account-specific** (tied to one or more chosen accounts). |
| PC-3 | A code has a status: Available, Reserved (planned for an account), Applied, Expired, Used up. Single-use codes move to Used up when applied. |
| PC-4 | The app flags codes expiring within 14 days and shows which accounts could use them. |
| PC-5 | When the scheduler plans a reactivation, it suggests the best eligible code for that account (most discounted value over the weeks needed) and the user confirms or edits. |
| PC-6 | Win-back offers are captured as codes of a special type, with the account they were sent to. They can be added by hand in v1. Parsing offer emails through a connected inbox is a later phase (section 9). |
| PC-7 | The app records the real discount that was applied after each order, so predicted and actual savings can be compared. |

## 5. Tracking and scheduling engine

### 5.1 Subscription and discount tracking

| ID | Requirement |
| --- | --- |
| TR-1 | Track every account's status: Active, Paused, Cancelled, or Unknown (sync failed). |
| TR-2 | For each account with a discount window, track start date, total weeks, weeks used, weeks remaining and the last discounted week (calculated end date). |
| TR-3 | Linked accounts are re-synced at least daily, and always before a skip or cancel cut-off, to confirm the real state matches the plan. |
| TR-4 | Each service has a **rule profile**: weekly skip cut-off (day and time), cancel cut-off, whether skipped weeks consume the discount window, whether discounts apply per box or per calendar week, and the minimum cancel-to-return gap before a win-back offer appears. |
| TR-5 | If real state differs from plan (box shipped when it should have been skipped, discount missing), the app raises an alert and recalculates the plan. |

### 5.2 Week assignment rules

The scheduler plans a rolling horizon (default 12 weeks) and re-plans after any change. Rules apply in priority order:

1. **One delivery per week.** At most one account across all services is set to Delivering in any week, unless the user marks a week as "allow two" (for example a holiday).
2. **Discount only.** An account is only eligible to deliver in a week if that week is covered by its discount window or a general code. No eligible discount means the account is not scheduled to deliver.
3. **Skip, never overlap.** Every active account that is not delivering in a given week is set to Skipped for that week, before the service's skip cut-off.
4. **No discount left means cancel.** If an account has no discounted weeks remaining and no code reserved, it is queued for cancellation (section 6).
5. **Continuity first.** Among eligible accounts, prefer the one whose discount window ends soonest, so windows are used before they expire, and prefer the order that leaves no uncovered week.
6. **Tie-breaks.** Highest discount value per box, then service the user prefers, then lowest cancel risk (shortest time to cut-off is treated as higher risk).
7. **Gaps are allowed.** If no account has an eligible discount for a week, that week stays empty. The app does not buy a full-price box to fill it unless the user explicitly adds an override.
8. **Locked weeks.** A week inside the service's skip cut-off is locked. The app does not change it and shows it read-only.

### 5.3 Reactivation planning

| ID | Requirement |
| --- | --- |
| RP-1 | For each cancelled account with a win-back offer, the scheduler picks a reactivation date so the first discounted delivery lands in the first uncovered week, allowing for the service's lead time before a box can ship. |
| RP-2 | Reactivation is a planned action shown in the calendar. By default it requires user approval; the user can switch an account to auto-reactivate once they trust the plan. |
| RP-3 | After reactivation the app immediately skips every week of that account except the assigned ones, and verifies the skip took effect. |
| RP-4 | The app shows a simple forecast: weeks covered, gaps, expected savings against the full-price baseline, and which accounts will need new offers soon. |

## 6. Auto-cancel, management views and notifications

### 6.1 Automatic cancellation

| ID | Requirement |
| --- | --- |
| AC-1 | An account is queued for cancellation when its last discounted week has been delivered (or skipped, if skips consume the window) and no further code or offer is reserved. |
| AC-2 | The cancel action runs after the final discounted box's skip cut-off has passed for the following week, so no full-price box can be created, and before the service's cancel cut-off. |
| AC-3 | **Safety check before cancel:** re-sync the account, confirm the next week is skipped or no box is scheduled, and confirm no unpaid or pending order exists. If the check fails, do not cancel silently; alert the user. |
| AC-4 | After cancel, the app confirms the status on the service and moves the account to Cancelled, then to Waiting if an offer is expected. |
| AC-5 | Cancel and reactivate actions are logged with timestamp, outcome and, where available, the service's confirmation. |
| AC-6 | If automation fails (login lost, page changed, service error), the app retries, then escalates to the user with a one-tap link to the service and a deadline. A failed cancel is the highest-priority alert. |
| AC-7 | The user can set cancellation to Auto, Ask first, or Remind only, per account. |

### 6.2 Management views

| View | Contents |
| --- | --- |
| Week calendar | Rows are weeks (rolling horizon). Each shows the delivering account and service, the discount applied, and status chips for every other account (Skipped, Inactive, Waiting, At risk). Locked weeks are marked. |
| Accounts | One card per account: service, status, health, discount weeks remaining and end date, next action and its date, savings so far. |
| Promo codes | Library with filters for service, scope, status and expiry. Shows which account each code is reserved for. |
| Timeline per account | History of reactivations, discounts used, skips and cancels. |
| Action queue | Upcoming automated actions (skip, reactivate, cancel) with approve, delay and cancel controls. |
| Savings | Actual versus full-price spend, by service and by month. |

The user can override any week by hand (force an account to deliver, force a skip, or block an account). Overrides are shown clearly, and the scheduler re-plans around them rather than undoing them.

### 6.3 Notifications

- **Urgent:** a cancel or skip action failed, an account would ship at full price, or login needs attention.
- **Upcoming:** a discount window ends within 2 weeks, a code expires within 14 days, or a reactivation is planned within 3 days.
- **Digest:** a weekly summary of what is delivering, what was skipped, and savings.
- Channels: push and email; each category can be switched off, but Urgent cannot be silenced entirely.

## 7. Data model and integration approach

### 7.1 Core entities

| Entity | Key fields |
| --- | --- |
| User | id, time zone, notification settings, planning horizon |
| Service | id, name, rule profile (skip cut-off, cancel cut-off, skips-count-toward-window flag, offer gap) |
| Account | id, user, service, nickname, email, link method, status, health, credential reference, delivery day, automation mode |
| PromoCode | id, service, code, scope, discount type and value, weeks, plan filter, expiry, status, source |
| CodeAccountLink | code, account (for account-specific codes and reservations) |
| DiscountWindow | id, account, source code or offer, start date, total weeks, weeks used, calculated end date |
| WeekAssignment | week start date, account (nullable), state, locked flag, manual override flag, reason |
| Action | id, account, type (skip, reactivate, cancel, sync), scheduled time, mode (auto, ask), status, result, evidence |
| Event log | timestamp, account, event, detail, source (sync, user, scheduler) |

### 7.2 Integration approach

The three services are not known to offer public APIs for customers to manage subscriptions, so integration is the main technical risk. Options, in order of preference:

1. **Official or partner APIs**, if any exist. Check first.
2. **User-authorised browser or device automation** that acts on the user's own accounts using the services' normal websites or apps, with the user completing any verification step.
3. **Manual mode** with reminders: the app plans, and the user taps through to the service to perform each action and confirms it. Manual mode must be fully usable, since it is the fallback when automation breaks.

Each service connector implements the same interface: sign in, read status, read discount and next delivery, skip week, unskip week, reactivate, cancel, and verify. Connectors report a confidence level and evidence (page text or confirmation number) for every action, so the scheduler can tell the difference between done and merely attempted.

### 7.3 Scheduler behaviour

- Runs on a timer and after every change (new code, sync result, manual override).
- Is deterministic and explainable: each week assignment stores the rule that produced it, shown in the UI as a one-line reason.
- Plans actions with a safety margin before each cut-off (default 24 hours) and shows the cut-off times in the user's time zone.

## 8. Security, privacy and non-functional requirements

| Area | Requirement |
| --- | --- |
| Credentials | Encrypted at rest with per-user keys, never logged, never displayed after entry. Prefer session tokens over stored passwords where a service allows it. Support deleting all credentials in one action. |
| Payment data | The app never collects or stores card numbers. Payment stays with each service. |
| Personal data | Store only what the plan needs (email, nickname, masked address, delivery day). Delete all data on account closure within 30 days. Follow Canadian privacy law (PIPEDA) for consent and retention. |
| Access | Sign-in with two-factor authentication. Re-authentication required before linking an account or enabling auto-cancel. |
| Audit | Every automated action is logged with its evidence and is visible to the user. |
| Reliability | Scheduled actions are idempotent and retried. A missed cancel or skip is treated as an incident. Target 99.5% uptime for the scheduler. |
| Time handling | All cut-offs are stored with the service's time zone and shown in the user's. Daylight saving changes are tested. |
| Resilience | Connector breakage must not stop the scheduler: affected accounts drop to Manual mode with an alert. |
| Platforms | Mobile-first (iOS and Android or a progressive web app) with a web view for the week calendar. |
| Accessibility | Meet WCAG 2.1 AA. Status is never conveyed by colour alone. |

## 9. Risks, phasing and open questions

### 9.1 Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Terms of service. Automating accounts, or running many accounts to collect new-customer or return offers, may breach a service's terms and could lead to account closure or voided discounts. | High | Get a legal read before building. Act only on the user's own accounts, with the user's consent, and never evade verification or fraud checks. Make Manual mode a first-class option. |
| Offer rules change without notice (length, eligibility, stacking, per-household or per-address limits). | High | Keep rules in per-service profiles, record actual discounts, and alert when predicted and actual differ. |
| Connectors break when a website or app changes. | High | Contract tests per connector, fast fallback to Manual mode, and a clear health state per account. |
| A cancel or skip fails and a full-price box ships. | High | Safety margins, verify-after-action, priority alerts, and Ask-first mode as the default for new users. |
| Win-back offers are not predictable, so gaps appear. | Medium | Show forecast gaps early, list accounts likely to receive offers, and never auto-buy full-price boxes. |
| Storing logins for several accounts is a security target. | High | Encryption, minimal retention, 2FA, and a preference for tokens over passwords. |

### 9.2 Phasing

| Phase | Content |
| --- | --- |
| 1. Manual planner (MVP) | Accounts and promo codes entered by hand, discount window tracking, week assignment engine, calendar, action queue and reminders. No automation. Proves the scheduling logic and the user value. |
| 2. Read-only sync | Linked accounts for HelloFresh, Chef's Plate and Good Food that import status, discounts and deliveries and detect drift from the plan. |
| 3. Actions | Automated skip, reactivate and cancel with approval, then optional auto mode with safety checks. |
| 4. Offer capture | Parse win-back offers from a connected inbox, and suggest the best code per reactivation. |
| 5. Extensions | More services, shared households, recipe selection, price history. |

### 9.3 Open questions

- Do any of the three services offer a partner API, or a supported way to authorise a third party?
- How does each service count skipped weeks against a discount window, and what is its skip and cancel cut-off?
- How long after cancelling does each service typically send a win-back offer, and are offers tied to the account, email, address or payment method?
- Do the services limit returns or discounts per household, address or card?
- Is this app for personal use only, or intended as a product for other users? That changes legal, security and support requirements substantially.
- Should the default for a week with no eligible discount be to leave it empty, or to allow a full-price box above a user-set price?

## 10. Delivery, packaging and release process

### 10.1 Packaging

- The app ships as one Docker image that serves the web portal and the scheduler from a single container, listening on port 3800 (from v0.3; v0.1 and v0.2 used port 8000).
- Configuration through environment variables; data kept on a mounted volume; a health endpoint for monitoring.
- The portal is responsive and works on mobile browsers.

### 10.2 Promo code capture by photo

| ID | Requirement |
| --- | --- |
| PC-8 | On mobile, the user can take a photo of a promo code (or choose one from the gallery) from the Add promo code screen. |
| PC-9 | The app reads the image with text recognition and proposes the code text, the likely service, the discount and weeks if printed, and the expiry date. |
| PC-10 | The user always sees an editable confirmation screen before anything is saved. Low-confidence fields are highlighted. |
| PC-11 | If no code is found, the app says so and offers a retake or manual entry. |
| PC-12 | Photos are used only for recognition and are deleted after confirmation unless the user chooses to keep them. |
| PC-13 | Live camera preview needs HTTPS; the portal must also work with the phone's standard camera or file picker so capture still works behind plain HTTP on a home network. |

### 10.3 Source control and automated publishing

- The project lives in a GitHub repository.
- A GitHub Actions workflow runs on every push to the main branch, builds the image, and pushes it to Docker Hub tagged with the version and `latest`.
- Docker Hub credentials are stored as repository secrets, never in the code.

### 10.4 Versioning

- The first build is v0.1. Every build increments the version (v0.2, v0.3, and so on).
- The version lives in one `VERSION` file, appears in the portal footer, and is used for the git tag and the Docker image tag.

### 10.5 Working agreement

- Requested changes are logged in the change log as they are sent; nothing is built until the instruction "build it and push it".
- Each change log entry carries a short commit message (50 characters or fewer) and a long commit message (250 characters or fewer).
- One zip is always kept current, containing the functional spec, the change log and the project files.

## 11. Implementation status

### v0.1 (built 2026-10-07): manual planner

| Area | Status | Notes |
| --- | --- | --- |
| Accounts | Built (manual only) | AL-1 manual method, nickname, status, per-account cancel mode. No linking, health state or sync (AL-2, AL-3, AL-7). |
| Promo codes | Built | PC-1 to PC-4, win-back codes tied to an account. Not built: suggested best code (PC-5), actual-versus-predicted discount (PC-7). |
| Photo capture | Built | PC-8 to PC-11 and PC-13 through the phone's camera or gallery picker. The photo is always discarded (PC-12); the option to keep it is not built. |
| Tracking and scheduler | Built | Rules 1 to 8 of section 5.2, service rule profile (skip cut-off, reactivation lead time, skips-use-window flag), past weeks counted as delivered. Daily sync (TR-3) not built. |
| Reactivation | Built as planned actions | RP-1 and RP-3 as queued actions you perform; forecast shows weeks covered and gaps only (RP-4 partly). |
| Auto-cancel | Built as planned actions | AC-1, AC-2, AC-4, AC-5, AC-7 as a queue with Done; the account status updates when you mark an action done. Safety check and retries (AC-3, AC-6) wait for sync. |
| Views | Partly built | Week calendar, accounts, promo codes, action queue, settings with activity log. Not built: per-account timeline, savings. |
| Notifications | Not built | The in-app action queue only. |
| Packaging and release | Built | Section 10.1 to 10.4: Docker image, GitHub Actions to Docker Hub, VERSION file. |
| Security | Minimal | Optional shared password. No 2FA. No credentials are stored because accounts are not linked. |

### 11.2 v0.3 (built 2026-10-07): linked accounts and automatic actions

Requirements LK-1 to LK-8 below, with how each was built. Differences from the wording are in the status table that follows.

| ID | Requirement |
| --- | --- |
| LK-1 | The user can link an account by entering its login (email and password). Logins are encrypted at rest with a key the operator supplies in an environment variable. The app refuses to store a login if no key is set. Passwords are never shown again or logged. Unlinking deletes the stored login. |
| LK-2 | One connector per service (HelloFresh, Chef's Plate, Good Food) signs in to the service's website with the user's own login and can: read status, read upcoming weeks (delivering, skipped, paused) and discounts, skip and unskip a week, reactivate, cancel, and verify the result. |
| LK-3 | A verification step (one-time code, CAPTCHA, email challenge) is never bypassed. The account moves to Needs attention and the user completes the sign-in. |
| LK-4 | Automatic status sync: at least daily, and before every skip and cancel cut-off, the app reads each linked account's status for the coming weeks and records it as the actual state for each week. Differences from the plan raise an alert and the plan is recalculated. |
| LK-5 | Automatic actions: when an account's mode is Auto, the app performs reactivate, skip and cancel at the planned time. Ask first requires approval in the portal. Remind only stays manual as in v0.2. Every action is verified by re-reading the account, retried on failure, and escalated if it still fails. |
| LK-6 | Safety checks before a cancel (AC-3): the account is re-read, the next week is skipped or has no box, and no unpaid or pending order exists. If any check fails, the cancel is not performed and the user is alerted. |
| LK-7 | Every automated action is stored in the activity log with time, result and evidence (page text or confirmation number). |
| LK-8 | Newly linked accounts start in dry-run mode: the connector reads and reports what it would do without changing anything. The user switches the account to Ask first or Auto after checking the results. |

Connector design note (CL-0007): connectors are Python Playwright flows with one page profile per service (paths and selectors, overridable in `connectors.json` without a rebuild), no stealth or bot evasion. The open-source mcp-hellofresh project was a reference only. Every action is verified by re-reading the account.

| Requirement | v0.3 status | Notes |
| --- | --- | --- |
| LK-1 | Built | Fernet encryption, key derived from `SECRET_KEY` (16+ characters). Linking is refused without the key. Unlink deletes the login. Changing the key means entering logins again. |
| LK-2 | Built, unverified against the live sites | Read status, read weeks, skip, unskip, reactivate, cancel for all three services. Page paths and selectors are starting guesses (HelloFresh and Chef's Plate share one layout assumption; Good Food paths are guesses). Reading discounts from the site is not built. |
| LK-3 | Built | Verification text (codes, CAPTCHA, check your email) stops the run and sets Needs attention. |
| LK-4 | Built, differs | Runs every 6 hours (`SYNC_HOURS`), on demand, and before every action. The plan is rebuilt after each read; a box the service shows on a locked week is adopted as committed; other differences are shown on the week plan and as an alert, and a planned box the service shows as skipped is un-skipped in Auto mode. |
| LK-5 | Built | Auto acts when due (skips 3 days before the cut-off; reactivate and cancel when due). Ask first waits for Approve on the Actions page. Every action is verified; after 3 failed attempts automatic tries stop. No retry delay beyond the next cycle. |
| LK-6 | Built, differs | Refuses if a payment problem is visible, or if a box after the last discounted one cannot be skipped. A pending unpaid order is detected only from payment wording on the page. |
| LK-7 | Built, differs | The log records time, result and a short status summary (counts of delivering/skipped weeks), not page text, to avoid storing personal data. `CONNECTOR_DEBUG=1` saves page text locally for fixing selectors. |
| LK-8 | Built | New links start in dry-run. Live changes can be switched on only after a successful sign-in test. |
| Port 3800 | Built | Dockerfile, health check, compose and README. |

Constraints: the services offer no public APIs, so connectors drive their websites and will break when those sites change; automating accounts may breach a service's terms (section 9.1); the app cannot read or act on an account until the login works and any verification step is completed by the user.
