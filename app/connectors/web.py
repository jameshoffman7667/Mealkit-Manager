"""Browser connector: drives a service's website with Playwright, signed in with the user's own login.

It never tries to get past a verification step and never fakes a browser identity. Every action is
followed by a fresh read in app/automation.py, which is what decides whether it worked.
"""
import re
from datetime import date
from typing import Optional

from .. import config
from .base import Connector, ConnectorError, NeedsVerification, RemoteState
from .parse import (detect_payment_issue, detect_verification, monday, parse_account_status,
                    parse_card)
from .profiles import SiteProfile

KEEP_WORDS = re.compile(r"keep|stay|never mind|go back|not now|with (my|the|your) plan|offer|discount|% off", re.I)


class WebConnector(Connector):
    def __init__(self, profile: SiteProfile, email: str, password: str):
        self.p = profile
        self._email = email
        self._password = password
        self._pw = self._browser = self.page = None
        self._today: Optional[date] = None

    # ----- session -----
    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ConnectorError("Playwright is not installed on this server.")
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = self._browser.new_context(locale="en-CA", viewport={"width": 1280, "height": 1600})
            self.page = ctx.new_page()
            self.page.set_default_timeout(20000)
        except Exception as exc:
            self.close()
            raise ConnectorError(f"The browser could not start: {exc}")
        try:
            self._login()
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._browser = self._pw = self.page = None

    # ----- helpers -----
    def _text(self) -> str:
        return self.page.inner_text("body")

    def _check(self, step: str) -> str:
        text = self._text()
        if config.debug_capture():
            d = config.data_dir() / "debug"
            d.mkdir(exist_ok=True)
            (d / f"{self.p.service_id}-{step}.txt").write_text(f"{self.page.url}\n\n{text}")
        if detect_verification(text):
            raise NeedsVerification(
                f"{self.p.service_id} asked for a verification step. Sign in once on the site yourself, "
                "then try again. The app never bypasses this.")
        return text

    def _goto(self, path: str, step: str) -> str:
        self.page.goto(self.p.base_url + path, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        return self._check(step)

    def _click(self, locator, what: str) -> None:
        loc = locator.first
        try:
            loc.wait_for(state="visible", timeout=5000)
            loc.click()
        except Exception:
            raise ConnectorError(f"Could not find the '{what}' button on {self.page.url}. "
                                 "The site may have changed; see connectors.json in the README.")
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

    def _settle(self) -> None:
        self._check("after-action")

    # ----- sign in -----
    def _login(self) -> None:
        self._goto(self.p.login_path, "login")
        try:
            self.page.locator(self.p.email_sel).first.fill(self._email)
            self.page.locator(self.p.password_sel).first.fill(self._password)
        except Exception:
            raise ConnectorError(f"Could not find the sign-in form at {self.p.base_url}{self.p.login_path}.")
        self._click(self.page.locator(self.p.submit_sel), "sign in")
        self._check("after-login")
        if self.page.locator(self.p.password_sel).count() and "login" in self.page.url.lower():
            raise ConnectorError("The service did not accept the login. Check the email and password.")

    # ----- reading -----
    def read_state(self, today: date) -> RemoteState:
        plan_text = self._goto(self.p.plan_path, "plan")
        status = parse_account_status(plan_text)
        if status is None:
            raise ConnectorError(f"Could not tell whether the plan is active at {self.page.url}.")
        deliv_text = self._goto(self.p.deliveries_path, "deliveries")
        weeks = {}
        for card in self.page.locator(self.p.card_sel).all():
            got = parse_card(card.inner_text(), today)
            if got:
                weeks.setdefault(got[0], got[1])
        issue = detect_payment_issue(plan_text) or detect_payment_issue(deliv_text)
        counts = {s: sum(1 for v in weeks.values() if v == s) for s in ("delivering", "skipped", "paused")}
        return RemoteState(status, weeks, issue,
                           f"status={status}, delivering={counts['delivering']}, skipped={counts['skipped']}, "
                           f"paused={counts['paused']}")

    def _card(self, week: date):
        self._goto(self.p.deliveries_path, "deliveries")
        for card in self.page.locator(self.p.card_sel).all():
            got = parse_card(card.inner_text(), self._today or date.today())
            if got and got[0] == week:
                return card
        raise ConnectorError(f"No delivery is listed for the week of {week}.")

    def _confirm(self, pattern: str) -> None:
        scope = self.page.get_by_role("dialog")
        scope = scope if scope.count() else self.page
        btn = scope.get_by_role("button", name=re.compile(pattern, re.I))
        try:
            btn.first.wait_for(state="visible", timeout=3000)
            btn.first.click()
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass  # many sites act without a confirmation step

    # ----- acting -----
    def skip(self, week: date) -> None:
        card = self._card(week)
        self._click(card.get_by_role("button", name=re.compile(r"^\s*skip", re.I))
                    .or_(card.get_by_role("link", name=re.compile(r"^\s*skip", re.I))), "skip")
        self._confirm(r"confirm|yes.*skip|skip (this )?(week|delivery)")
        self._settle()

    def unskip(self, week: date) -> None:
        card = self._card(week)
        self._click(card.get_by_role("button", name=re.compile(r"un-?skip|restore|add back|resume", re.I))
                    .or_(card.get_by_role("link", name=re.compile(r"un-?skip|restore|add back|resume", re.I))),
                    "unskip")
        self._confirm(r"confirm|yes")
        self._settle()

    def reactivate(self) -> None:
        self._goto(self.p.plan_path, "plan")
        self._click(self.page.get_by_role("button", name=re.compile(r"reactivate|restart|resume|come back", re.I))
                    .or_(self.page.get_by_role("link", name=re.compile(r"reactivate|restart|resume|come back", re.I))),
                    "reactivate")
        self._confirm(r"confirm|yes|reactivate|restart|resume")
        self._settle()

    def cancel(self) -> None:
        self._goto(self.p.plan_path, "plan")
        self._click(self.page.get_by_role("button", name=re.compile(r"cancel (plan|subscription)|cancel", re.I))
                    .or_(self.page.get_by_role("link", name=re.compile(r"cancel (plan|subscription)|cancel", re.I))),
                    "cancel plan")
        # Retention offers and surveys: continue through them, never accept an offer to stay.
        go = re.compile(r"(confirm|yes|continue|proceed).*|cancel (plan|subscription|anyway)|no thanks|skip survey", re.I)
        for _ in range(6):
            self._settle()
            btns = self.page.get_by_role("button", name=go)
            usable = [b for b in btns.all() if b.is_visible() and not KEEP_WORDS.search(b.inner_text() or "")]
            if not usable:
                break
            usable[0].click()
            try:
                self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
        self._settle()
