"""Sign-in logic of the browser connector (P-7), against a fake page. No Playwright or network needed."""
import pytest

from app.connectors import profiles
from app.connectors.base import ConnectorError
from app.connectors.parse import site_error_text, still_on_login
from app.connectors.web import WebConnector


class Loc:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    def wait_for(self, state="visible", timeout=0):
        if self.sel in self.page.missing:
            raise TimeoutError(self.sel)

    def fill(self, text):
        self.page.filled.append((self.sel, text))

    def click(self):
        self.page.actions.append("click")
        self.page.after_submit()

    def press(self, key):
        self.page.actions.append("press " + key)
        self.page.after_submit()

    def count(self):
        return 1 if self.page.password_box_visible and self.sel == self.page.prof.password_sel else 0

    def all_inner_texts(self):
        return self.page.error_texts if self.sel == self.page.prof.error_sel else []


class FakePage:
    """Stays on the login page unless `accepts` is true; `missing` selectors are never found."""
    def __init__(self, prof, accepts=True, missing=(), error_texts=()):
        self.prof, self.accepts, self.missing = prof, accepts, set(missing)
        self.error_texts = list(error_texts)
        self.url = prof.base_url + prof.login_path
        self.password_box_visible = True
        self.filled, self.actions, self.clock = [], [], 0
        self.pending = False

    def goto(self, url, wait_until=None):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass

    def inner_text(self, sel):
        return "Welcome"

    def locator(self, sel):
        return Loc(self, sel)

    def after_submit(self):
        self.pending = True

    def wait_for_timeout(self, ms):
        self.clock += ms
        # the site moves on after 2.5 seconds, never before (a check made at once would still see the login page)
        if self.pending and self.accepts and self.clock >= 2500:
            self.url = self.prof.base_url + "/my-account"
            self.password_box_visible = False


def connector(service, **kw):
    prof = profiles.PROFILES[service]
    c = WebConnector(prof, "me@example.com", "pw")
    c.page = FakePage(prof, **kw)
    return c


def test_live_login_selectors_match_the_pages_read_on_2026_11_14():
    hf, cp = profiles.PROFILES["hellofresh"], profiles.PROFILES["chefsplate"]
    assert 'input[name="username"]' in hf.email_sel and hf.submit_sel == 'button[type="submit"]'
    assert "#INPUT_EMAIL" in cp.email_sel and "#INPUT_PASSWORD" in cp.password_sel


def test_login_waits_for_the_site_to_move_on():
    c = connector("hellofresh")
    c._login()                                           # accepted after 2.5 s: must not be reported as a failure
    assert c.page.filled[0] == (profiles.PROFILES["hellofresh"].email_sel, "me@example.com")
    assert c.page.actions == ["click"]


def test_chefsplate_without_a_matching_button_presses_enter():
    prof = profiles.PROFILES["chefsplate"]
    c = connector("chefsplate", missing={prof.submit_sel})
    c._login()
    assert c.page.actions == ["press Enter"]


def test_missing_form_gives_the_form_message():
    prof = profiles.PROFILES["chefsplate"]
    c = connector("chefsplate", missing={prof.email_sel})
    with pytest.raises(ConnectorError, match="Could not find the sign-in form at https://www.chefsplate.com/login"):
        c._login()


def test_rejected_login_reports_the_sites_own_error():
    c = connector("hellofresh", accepts=False, error_texts=["", "  Incorrect email\n or password  "])
    with pytest.raises(ConnectorError, match='did not accept the login: "Incorrect email or password"'):
        c._login()


def test_rejected_login_without_error_text_still_fails_clearly():
    c = connector("hellofresh", accepts=False)
    with pytest.raises(ConnectorError, match="did not accept the login, or the page did not move on"):
        c._login()


def test_helpers():
    assert still_on_login("https://x/login", True) and not still_on_login("https://x/login", False)
    assert not still_on_login("https://x/my-account", True)
    assert site_error_text(["", "  a   b "]) == "a b" and site_error_text([]) == "" and len(site_error_text(["x" * 500])) == 160
