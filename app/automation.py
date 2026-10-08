"""Linked-account automation: read each account's real state, then reactivate, skip and cancel on time.

Rules that keep this safe (spec section 11.2):
  * Nothing changes on a service unless the account is linked, in Auto mode and switched out of dry-run.
  * Every change is followed by a fresh read; it only counts as done if the read shows the new state.
  * A cancel is refused if a payment problem is visible or a later box is still going to ship.
  * Verification steps (codes, CAPTCHA) are never bypassed: the account is flagged for the user.
"""
import threading
from datetime import date, datetime, timedelta
from typing import Optional

from . import config, connectors, db, vault
from . import scheduler as sch
from .connectors.base import ConnectorError, NeedsVerification
from .state import load_state

LOCK = threading.Lock()
SKIP_LEAD_DAYS = 3      # skip this many days before the service's cut-off, not weeks ahead
MAX_FAILURES = 3        # automatic attempts per action before it is left for the user


def _now() -> str:
    return datetime.now().isoformat(timespec="minutes")


def _open(row):
    email, password = vault.decrypt(row["cred_enc"])
    return connectors.FACTORY(row["service_id"], email, password)


def complete_action(c, type_: str, account_id: int, wk: date) -> None:
    """Record that an action has been carried out (by the user or by the app) and update the account."""
    key = f"{type_}:{account_id}:{wk.isoformat()}"
    if type_ == "reactivate":
        c.execute("UPDATE accounts SET status='active' WHERE id=?", (account_id,))
    elif type_ == "cancel":
        planned = c.execute(
            "SELECT 1 FROM plan WHERE week_start=? AND account_id=? AND state='delivering'",
            (wk.isoformat(), account_id),
        ).fetchone()
        c.execute("UPDATE accounts SET status='cancelled' WHERE id=?", (account_id,))
        if planned:  # the box for this week is already locked in, keep it in the plan
            c.execute("INSERT INTO overrides(week_start, kind, account_id, committed) "
                      "VALUES (?, 'force', ?, 1)", (wk.isoformat(), account_id))
    elif type_ != "skip":
        raise ValueError("Unknown action")
    c.execute("INSERT OR IGNORE INTO actions_done(key) VALUES (?)", (key,))
    db.log(c, account_id, f"{type_}_done", f"week of {wk}")


# ---------- reading ----------
def _attention(aid: int, exc: Exception) -> dict:
    msg = str(exc)[:240] or exc.__class__.__name__
    with db.session() as c:
        c.execute("UPDATE accounts SET link_state='attention', link_msg=? WHERE id=?", (msg, aid))
        db.log(c, aid, "sync_failed", msg)
    return {"ok": False, "msg": msg}


def _store_remote(c, aid: int, rs) -> None:
    c.execute("DELETE FROM remote_weeks WHERE account_id=?", (aid,))
    for wk, st in rs.weeks.items():
        c.execute("INSERT INTO remote_weeks(account_id, week_start, state, checked_at) VALUES (?,?,?,?)",
                  (aid, wk.isoformat(), st, _now()))
    c.execute("UPDATE accounts SET remote_status=?, last_sync=?, link_state='linked', link_msg='' WHERE id=?",
              (rs.status, _now(), aid))


def sync_account(aid: int, today: Optional[date] = None) -> dict:
    """Sign in, read plan status and the coming weeks, and store them as the actual state."""
    today = today or config.today()
    with db.session() as c:
        row = c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
    if not row or not row["cred_enc"]:
        return {"ok": False, "msg": "This account is not linked."}
    try:
        with _open(row) as cn:
            rs = cn.read_state(today)
    except (ConnectorError, vault.VaultError) as exc:
        return _attention(aid, exc)
    except Exception as exc:  # a broken site must not stop the other accounts
        return _attention(aid, ConnectorError(f"Unexpected error: {exc}"))
    with db.session() as c:
        _store_remote(c, aid, rs)
        if rs.status != row["status"]:
            c.execute("UPDATE accounts SET status=? WHERE id=?", (rs.status, aid))
            db.log(c, aid, "status_synced", f"{row['status']} -> {rs.status} (as shown by the service)")
        db.log(c, aid, "sync_ok", rs.evidence)
    return {"ok": True, "msg": rs.evidence, "state": rs}


def reconcile(c) -> int:
    """Where the service shows a box on a locked week the plan did not expect, trust the service."""
    st = load_state(c)
    changed = 0
    existing = {(o.week.isoformat()) for o in st["overrides"] if o.kind in ("force", "empty")}
    for w in st["plan"].weeks:
        wk = w.start.isoformat()
        shipping = [a.id for a in st["accounts"] if st["remote"].get((a.id, wk)) == "delivering"]
        if len(shipping) > 1:
            names = ", ".join(st["acct_by_id"][i].nickname for i in shipping)
            _log_once(c, f"double:{wk}:{names}", None, "double_delivery", f"Week of {wk}: {names} all show a box")
        if shipping and wk not in existing:
            aid = shipping[0]
            cell = w.cells.get(aid)
            if cell and cell.state != "delivering" and cell.locked:
                c.execute("INSERT INTO overrides(week_start, kind, account_id, committed) VALUES (?, 'force', ?, 1)",
                          (wk, aid))
                db.log(c, aid, "plan_adjusted", f"Week of {wk}: the service shows a locked box, plan updated")
                changed += 1
                existing.add(wk)
    return changed


def _log_once(c, key: str, aid, event: str, detail: str) -> None:
    k = "logged:" + key
    if db.get_setting(c, k, "") != "1":
        db.set_setting(c, k, "1")
        db.log(c, aid, event, detail)


# ---------- acting ----------
def _fail(c, key: str, aid: int, msg: str) -> str:
    n = int(db.get_setting(c, "fail:" + key, "0")) + 1
    db.set_setting(c, "fail:" + key, str(n))
    suffix = " Automatic attempts stopped; do it by hand or approve it in the Actions page." if n >= MAX_FAILURES else ""
    db.log(c, aid, "action_failed", f"{key}: {msg}{suffix}")
    return msg


def execute_action(type_: str, aid: int, week: date, today: Optional[date] = None) -> tuple:
    """Perform one action on the service and verify it. Returns (ok, message)."""
    today = today or config.today()
    key = f"{type_}:{aid}:{week.isoformat()}"
    with db.session() as c:
        row = c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
        cutoff = c.execute("SELECT skip_cutoff_days FROM services WHERE id=?",
                           (row["service_id"],)).fetchone()["skip_cutoff_days"] if row else 5
    if not row or not row["cred_enc"] or row["link_state"] != "linked":
        return False, "The account is not linked."
    try:
        with _open(row) as cn:
            pre = last = cn.read_state(today)
            msg = ""
            if type_ == "skip":
                if pre.weeks.get(week) != "skipped":
                    if week not in pre.weeks:
                        raise ConnectorError(f"The service lists no delivery for the week of {week}.")
                    cn.skip(week)
                    post = cn.read_state(today)
                    if post.weeks.get(week) != "skipped":
                        raise ConnectorError(f"The week of {week} still does not show as skipped.")
                    msg, last = post.evidence, post
            elif type_ == "unskip":
                if pre.weeks.get(week) == "skipped":
                    cn.unskip(week)
                    post = cn.read_state(today)
                    if post.weeks.get(week) != "delivering":
                        raise ConnectorError(f"The week of {week} still does not show as delivering.")
                    msg, last = post.evidence, post
            elif type_ == "reactivate":
                if pre.status != "active":
                    cn.reactivate()
                    post = cn.read_state(today)
                    if post.status != "active":
                        raise ConnectorError("The plan still does not show as active.")
                    msg, last = post.evidence, post
            elif type_ == "cancel":
                if pre.status == "active":
                    if pre.pending_issue:
                        raise ConnectorError(f"Cancel not performed: the service shows '{pre.pending_issue}'.")
                    later = sorted(w for w, s in pre.weeks.items() if w > week and s == "delivering")
                    for w in later:  # boxes after the last discounted one must not ship
                        if w - timedelta(days=cutoff) > today:
                            cn.skip(w)
                    if later:
                        mid = cn.read_state(today)
                        still = sorted(w for w, s in mid.weeks.items() if w > week and s == "delivering")
                        if still:
                            raise ConnectorError("Cancel not performed: boxes are still scheduled for "
                                                 + ", ".join(w.isoformat() for w in still) + ".")
                    cn.cancel()
                    post = cn.read_state(today)
                    if post.status != "cancelled":
                        raise ConnectorError("The plan still does not show as cancelled.")
                    msg, last = post.evidence, post
            else:
                return False, "Unknown action."
    except NeedsVerification as exc:
        with db.session() as c:
            c.execute("UPDATE accounts SET link_state='attention', link_msg=? WHERE id=?", (str(exc)[:240], aid))
            return False, _fail(c, key, aid, str(exc))
    except (ConnectorError, vault.VaultError) as exc:
        with db.session() as c:
            return False, _fail(c, key, aid, str(exc))
    except Exception as exc:
        with db.session() as c:
            return False, _fail(c, key, aid, f"Unexpected error: {exc}")
    with db.session() as c:
        _store_remote(c, aid, last)
        if type_ != "unskip":
            complete_action(c, type_, aid, week)
        db.log(c, aid, f"{type_}_auto", f"week of {week}. {msg or 'Already in place'}")
        db.set_setting(c, "fail:" + key, "0")
    return True, msg or "Already in place."


def run_cycle(today: Optional[date] = None, only_sync: bool = False) -> dict:
    """Sync every linked account, reconcile the plan, then carry out due actions for Auto accounts."""
    today = today or config.today()
    result = {"synced": 0, "failed": 0, "performed": 0, "dry_run": 0, "skipped": ""}
    if not LOCK.acquire(blocking=False):
        result["skipped"] = "A run is already in progress."
        return result
    try:
        if not config.automation_enabled() or not vault.configured():
            result["skipped"] = "Automation is off or SECRET_KEY is not set."
            return result
        with db.session() as c:
            if db.get_setting(c, "automation_paused", "0") == "1":
                result["skipped"] = "Automation is paused in Settings."
                return result
            ids = [r["id"] for r in c.execute("SELECT id FROM accounts WHERE cred_enc != ''")]
        for aid in ids:
            r = sync_account(aid, today)
            result["synced" if r["ok"] else "failed"] += 1
        with db.session() as c:
            reconcile(c)
            db.set_setting(c, "last_cycle", _now() + f" ({result['synced']} synced, {result['failed']} failed)")
        if only_sync:
            return result
        with db.session() as c:
            st = load_state(c)
            rows = {r["id"]: r for r in c.execute("SELECT * FROM accounts")}
        todo = []
        for a in st["actions"]:
            lead = SKIP_LEAD_DAYS if a.type == "skip" else 0
            if a.due <= today + timedelta(days=lead):
                todo.append((a.type, a.account_id, a.week))
        for d in st["drift"]:  # planned box but the service shows it skipped: put it back
            if d["planned"] == "delivering" and d["actual"] == "skipped":
                cutoff = st["services"][st["acct_by_id"][d["account_id"]].service_id].skip_cutoff_days
                if d["week"] - timedelta(days=cutoff) >= today:
                    todo.append(("unskip", d["account_id"], d["week"]))
        for type_, aid, wk in todo:
            row = rows.get(aid)
            if not row or row["link_state"] != "linked" or row["automation"] != "auto":
                continue
            key = f"{type_}:{aid}:{wk.isoformat()}"
            with db.session() as c:
                if int(db.get_setting(c, "fail:" + key, "0")) >= MAX_FAILURES:
                    continue
                if row["dry_run"]:
                    _log_once(c, f"dry:{key}:{today}", aid, "dry_run",
                              f"Would {type_} the week of {wk} (dry run, nothing changed)")
                    result["dry_run"] += 1
                    continue
            ok, _msg = execute_action(type_, aid, wk, today)
            result["performed"] += 1 if ok else 0
        return result
    finally:
        LOCK.release()
