"""Automation tests with a fake service site. They need no web framework and no browser."""
from datetime import date, timedelta

import pytest

from app import automation, config, connectors, db, vault
from app.connectors.base import Connector, ConnectorError, NeedsVerification, RemoteState
from app.state import load_state

TODAY = date(2026, 10, 7)          # a Wednesday; this week starts Oct 5
W = lambda m, d: date(2026, m, d)  # noqa: E731


class Site:
    """What a service's website currently shows for one account."""
    def __init__(self, status="active", weeks=None, pending="", verify=False, broken_skip=False):
        self.status, self.weeks, self.pending = status, dict(weeks or {}), pending
        self.verify, self.broken_skip = verify, broken_skip
        self.calls = []


class FakeConnector(Connector):
    def __init__(self, site):
        self.site = site

    def __enter__(self):
        if self.site.verify:
            raise NeedsVerification("asked for a code")
        return self

    def read_state(self, today):
        return RemoteState(self.site.status, dict(self.site.weeks), self.site.pending, "fake read")

    def skip(self, week):
        self.site.calls.append(("skip", week))
        if not self.site.broken_skip:
            self.site.weeks[week] = "skipped"

    def unskip(self, week):
        self.site.calls.append(("unskip", week))
        self.site.weeks[week] = "delivering"

    def reactivate(self):
        self.site.calls.append(("reactivate",))
        self.site.status = "active"

    def cancel(self):
        self.site.calls.append(("cancel",))
        self.site.status = "cancelled"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "a-long-enough-secret-key")
    monkeypatch.setattr(config, "today", lambda: TODAY)
    sites = {}
    monkeypatch.setattr(connectors, "FACTORY", lambda sid, email, pw: FakeConnector(sites[email]))
    db.init()
    return sites


def add(sites, nick, service, site, mode="auto", dry=0, window=None, status="active", linked=True):
    email = f"{nick}@x.test"
    sites[email] = site
    with db.session() as c:
        cur = c.execute(
            "INSERT INTO accounts(service_id, nickname, email, status, automation, link_state, cred_enc, dry_run) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (service, nick, email, status, mode, "linked" if linked else "unlinked",
             vault.encrypt(email, "pw") if linked else "", dry))
        aid = cur.lastrowid
        if window:
            c.execute("INSERT INTO windows(account_id, label, start_date, weeks) VALUES (?,?,?,?)",
                      (aid, "offer", window[0].isoformat(), window[1]))
    return aid


def acct(aid):
    with db.session() as c:
        return c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()


def events(name):
    with db.session() as c:
        return [r["detail"] for r in c.execute("SELECT detail FROM event_log WHERE event=?", (name,))]


def two_accounts(sites, **b_kw):
    a = add(sites, "A", "hellofresh", Site(weeks={W(10, 5): "delivering", W(10, 12): "delivering"}),
            mode="remind", window=(W(10, 5), 2))
    b = add(sites, "B", "chefsplate", Site(weeks={W(10, 12): "delivering", W(10, 19): "delivering"}),
            window=(W(10, 5), 4), **b_kw)
    return a, b


def test_sync_stores_actual_weeks_and_status(env):
    a, b = two_accounts(env)
    env["B@x.test"].status = "paused"
    res = automation.sync_account(b, TODAY)
    assert res["ok"]
    with db.session() as c:
        rows = {r["week_start"]: r["state"] for r in c.execute("SELECT * FROM remote_weeks WHERE account_id=?", (b,))}
        assert rows == {"2026-10-12": "delivering", "2026-10-19": "delivering"}
    assert acct(b)["remote_status"] == "paused" and acct(b)["status"] == "paused"
    assert acct(b)["link_state"] == "linked" and acct(b)["last_sync"]
    assert events("status_synced")


def test_dry_run_changes_nothing(env):
    a, b = two_accounts(env, dry=1)
    res = automation.run_cycle(TODAY)
    assert res["dry_run"] >= 1 and res["performed"] == 0
    assert env["B@x.test"].calls == []
    assert any("Would skip" in d for d in events("dry_run"))


def test_auto_skip_is_performed_and_verified(env):
    a, b = two_accounts(env)
    res = automation.run_cycle(TODAY)
    assert res["performed"] == 1
    assert env["B@x.test"].calls == [("skip", W(10, 12))]
    assert env["B@x.test"].weeks[W(10, 12)] == "skipped"
    with db.session() as c:
        assert c.execute("SELECT 1 FROM actions_done WHERE key=?", ("skip:%d:2026-10-12" % b,)).fetchone()
    # a second run finds nothing left to do
    assert automation.run_cycle(TODAY)["performed"] == 0
    assert env["B@x.test"].calls == [("skip", W(10, 12))]
    assert events("skip_auto")


def test_unverified_skip_is_not_marked_done(env):
    a, b = two_accounts(env)
    env["B@x.test"].broken_skip = True
    res = automation.run_cycle(TODAY)
    assert res["performed"] == 0
    with db.session() as c:
        assert not c.execute("SELECT 1 FROM actions_done").fetchone()
    assert any("still does not show as skipped" in d for d in events("action_failed"))


def test_ask_mode_waits_for_approval(env):
    a, b = two_accounts(env, mode="ask")
    automation.run_cycle(TODAY)
    assert env["B@x.test"].calls == []
    ok, _ = automation.execute_action("skip", b, W(10, 12), TODAY)   # what the Approve button does
    assert ok and env["B@x.test"].calls == [("skip", W(10, 12))]


def test_verification_step_flags_account(env):
    a, b = two_accounts(env)
    env["B@x.test"].verify = True
    res = automation.run_cycle(TODAY)
    assert res["failed"] == 1 and res["performed"] == 0
    row = acct(b)
    assert row["link_state"] == "attention" and "code" in row["link_msg"]


def single(sites, site, **kw):
    return add(sites, "A", "hellofresh", site, window=(W(10, 5), 1), **kw)


def test_cancel_skips_later_unlocked_box_then_cancels(env):
    a = single(env, Site(weeks={W(10, 5): "delivering", W(10, 19): "delivering"}))
    res = automation.run_cycle(TODAY)
    site = env["A@x.test"]
    assert site.calls == [("skip", W(10, 19)), ("cancel",)] and res["performed"] == 1
    assert acct(a)["status"] == "cancelled"
    with db.session() as c:   # the locked box this week stays in the plan
        assert c.execute("SELECT 1 FROM overrides WHERE kind='force' AND committed=1").fetchone()


def test_cancel_refused_when_payment_problem(env):
    a = single(env, Site(weeks={W(10, 5): "delivering"}, pending="payment failed"))
    automation.run_cycle(TODAY)
    assert env["A@x.test"].calls == [] and env["A@x.test"].status == "active"
    assert any("payment failed" in d for d in events("action_failed"))


def test_cancel_refused_when_locked_box_still_ships(env):
    a = single(env, Site(weeks={W(10, 5): "delivering", W(10, 12): "delivering"}))   # Oct 12 is past cut-off
    automation.run_cycle(TODAY)
    assert ("cancel",) not in env["A@x.test"].calls
    assert any("still scheduled" in d for d in events("action_failed"))


def test_reconcile_trusts_a_locked_box_the_service_shows(env):
    a, b = two_accounts(env, mode="remind")
    # the plan has A delivering this week, but B's box for this (locked) week is the one that will ship
    env["A@x.test"].weeks[W(10, 5)] = "skipped"
    env["B@x.test"].weeks[W(10, 5)] = "delivering"
    automation.sync_account(a, TODAY)
    automation.sync_account(b, TODAY)
    with db.session() as c:
        assert load_state(c)["plan"].weeks[0].delivering == a
        assert automation.reconcile(c) == 1
        assert automation.reconcile(c) == 0          # nothing more to adjust
        st = load_state(c)
    assert st["plan"].weeks[0].delivering == b
    assert events("plan_adjusted")


def test_drift_is_reported(env):
    a, b = two_accounts(env, mode="remind")
    env["A@x.test"].weeks[W(10, 19)] = "delivering"
    automation.sync_account(a, TODAY)
    with db.session() as c:
        st = load_state(c)
    assert st["drift"] and st["drift"][0]["actual"] == "delivering"


def test_unlinked_and_paused_do_nothing(env, monkeypatch):
    a, b = two_accounts(env)
    with db.session() as c:
        db.set_setting(c, "automation_paused", "1")
    assert automation.run_cycle(TODAY)["skipped"]
    assert env["B@x.test"].calls == []
    monkeypatch.delenv("SECRET_KEY")
    assert "SECRET_KEY" in automation.run_cycle(TODAY)["skipped"]


def test_migration_adds_columns_to_old_database(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    con = sqlite3.connect(tmp_path / "mealkit.db")
    con.executescript("CREATE TABLE services(id TEXT PRIMARY KEY, name TEXT NOT NULL, skip_cutoff_days INTEGER "
                      "NOT NULL DEFAULT 5, reactivate_lead_days INTEGER NOT NULL DEFAULT 10, skips_consume_window "
                      "INTEGER NOT NULL DEFAULT 0);"
                      "CREATE TABLE accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, service_id TEXT NOT NULL, "
                      "nickname TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active', "
                      "automation TEXT NOT NULL DEFAULT 'ask', note TEXT NOT NULL DEFAULT '', "
                      "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
                      "INSERT INTO accounts(service_id, nickname) VALUES ('hellofresh','old');")
    con.commit(); con.close()
    db.init()
    row = acct(1)
    assert row["nickname"] == "old" and row["link_state"] == "unlinked" and row["dry_run"] == 1
