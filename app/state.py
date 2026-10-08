"""Loads everything the pages need and refreshes the stored plan."""
from datetime import date

from . import config, db
from . import scheduler as sch


def sync_past(c, today: date) -> None:
    """Count weeks that have passed as delivered, then drop stale rows."""
    wk0 = sch.monday(today).isoformat()
    for r in c.execute(
        "SELECT account_id, window_id, week_start FROM plan "
        "WHERE state='delivering' AND window_id IS NOT NULL AND week_start < ?",
        (wk0,),
    ).fetchall():
        c.execute(
            "INSERT OR IGNORE INTO deliveries(account_id, window_id, week_start) VALUES (?,?,?)",
            (r["account_id"], r["window_id"], r["week_start"]),
        )
    c.execute("DELETE FROM plan WHERE week_start < ?", (wk0,))
    c.execute("DELETE FROM overrides WHERE week_start < ?", (wk0,))


def expire_codes(c, today: date) -> None:
    c.execute(
        "UPDATE promo_codes SET status='expired' "
        "WHERE expiry IS NOT NULL AND expiry < ? AND status IN ('available','reserved')",
        (today.isoformat(),),
    )


def week_drift(plan, remote: dict) -> list:
    """Weeks where the service shows something different from the plan."""
    out = []
    for w in plan.weeks:
        for aid, cell in w.cells.items():
            actual = remote.get((aid, w.start.isoformat()))
            if actual is None:
                continue
            if (cell.state == "delivering" and actual in ("skipped", "paused")) or \
               (cell.state != "delivering" and actual == "delivering"):
                out.append({"week": w.start, "account_id": aid, "planned": cell.state, "actual": actual})
    return out


def load_state(c) -> dict:
    today = config.today()
    sync_past(c, today)
    expire_codes(c, today)
    svc_rows = c.execute("SELECT * FROM services ORDER BY name").fetchall()
    services = {
        r["id"]: sch.Svc(r["id"], r["name"], r["skip_cutoff_days"], r["reactivate_lead_days"],
                         bool(r["skips_consume_window"]))
        for r in svc_rows
    }
    acct_rows = c.execute("SELECT * FROM accounts ORDER BY service_id, nickname").fetchall()
    accounts = [sch.Acct(r["id"], r["service_id"], r["nickname"], r["status"]) for r in acct_rows]
    used = {r["window_id"]: r["n"] for r in c.execute(
        "SELECT window_id, COUNT(*) n FROM deliveries GROUP BY window_id")}
    win_rows = c.execute("SELECT * FROM windows ORDER BY start_date, id").fetchall()
    windows = [
        sch.Win(r["id"], r["account_id"], date.fromisoformat(r["start_date"]), r["weeks"],
                used.get(r["id"], 0), r["discount_value"], r["label"])
        for r in win_rows
    ]
    ovr_rows = c.execute("SELECT * FROM overrides ORDER BY week_start, id").fetchall()
    overrides = [
        sch.Ovr(date.fromisoformat(r["week_start"]), r["kind"], r["account_id"], bool(r["committed"]))
        for r in ovr_rows
    ]
    horizon = int(db.get_setting(c, "horizon_weeks", str(config.horizon_default())))
    plan = sch.build_plan(today, accounts, services, windows, overrides, horizon)

    c.execute("DELETE FROM plan WHERE week_start >= ?", (sch.monday(today).isoformat(),))
    for w in plan.weeks:
        for aid, cell in w.cells.items():
            c.execute(
                "INSERT OR REPLACE INTO plan(week_start, account_id, state, window_id, reason) "
                "VALUES (?,?,?,?,?)",
                (w.start.isoformat(), aid, cell.state, cell.window_id, cell.reason),
            )
    remote = {(r["account_id"], r["week_start"]): r["state"]
              for r in c.execute("SELECT account_id, week_start, state FROM remote_weeks")}
    done = {r["key"] for r in c.execute("SELECT key FROM actions_done")}
    actions = [a for a in plan.actions if a.key not in done]
    return {
        "today": today, "services": services, "svc_rows": svc_rows, "accounts": accounts,
        "acct_rows": acct_rows, "windows": windows, "win_rows": win_rows, "overrides": overrides,
        "ovr_rows": ovr_rows, "plan": plan, "actions": actions, "horizon": horizon, "used": used,
        "acct_by_id": {a.id: a for a in accounts},
        "remote": remote, "drift": week_drift(plan, remote),
    }
