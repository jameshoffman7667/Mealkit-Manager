import base64
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, ocr
from . import scheduler as sch

BASE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app):
    db.init()
    yield


app = FastAPI(title="Meal Kit Subscription Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["version"] = config.version


# ---------- auth (optional) ----------
@app.middleware("http")
async def basic_auth(request: Request, call_next):
    pw = config.app_password()
    if pw and request.url.path != "/health":
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                given = base64.b64decode(header[6:]).decode().partition(":")[2]
                ok = secrets.compare_digest(given.encode(), pw.encode())
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="mealkit"'})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "version": config.version()}


# ---------- helpers ----------
def parse_date(value: str, field: str, required: bool = True) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        if required:
            raise HTTPException(400, f"{field} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{field} must be a date (YYYY-MM-DD)")


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


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
    done = {r["key"] for r in c.execute("SELECT key FROM actions_done")}
    actions = [a for a in plan.actions if a.key not in done]
    return {
        "today": today, "services": services, "svc_rows": svc_rows, "accounts": accounts,
        "acct_rows": acct_rows, "windows": windows, "win_rows": win_rows, "overrides": overrides,
        "ovr_rows": ovr_rows, "plan": plan, "actions": actions, "horizon": horizon, "used": used,
        "acct_by_id": {a.id: a for a in accounts},
    }


def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)


# ---------- dashboard ----------
@app.get("/")
def dashboard(request: Request):
    with db.session() as c:
        st = load_state(c)
    plan = st["plan"]
    horizon_weeks = len([w for w in plan.weeks if not w.empty])
    upcoming = [a for a in st["actions"] if a.due <= st["today"] + timedelta(days=14)]
    return render(
        request, "dashboard.html", st=st, plan=plan, upcoming=upcoming[:8],
        coverage=(plan.covered, horizon_weeks), active=sum(a.status == "active" for a in st["accounts"]),
    )


@app.get("/api/plan")
def api_plan():
    with db.session() as c:
        st = load_state(c)
    return JSONResponse({
        "today": st["today"].isoformat(),
        "weeks": [
            {
                "week": w.start.isoformat(),
                "delivering": w.delivering,
                "cells": {str(k): {"state": v.state, "reason": v.reason, "locked": v.locked,
                                   "full_price": v.full_price} for k, v in w.cells.items()},
            }
            for w in st["plan"].weeks
        ],
        "actions": [
            {"type": a.type, "account_id": a.account_id, "due": a.due.isoformat(),
             "week": a.week.isoformat(), "note": a.note}
            for a in st["actions"]
        ],
    })


# ---------- accounts ----------
@app.get("/accounts")
def accounts_page(request: Request):
    with db.session() as c:
        st = load_state(c)
    wins_by_acct: dict = {}
    for r in st["win_rows"]:
        wins_by_acct.setdefault(r["account_id"], []).append(r)
    return render(request, "accounts.html", st=st, wins_by_acct=wins_by_acct,
                  ends=st["plan"].window_ends)


@app.post("/accounts")
def create_account(service_id: str = Form(...), nickname: str = Form(...), email: str = Form(""),
                   status: str = Form("active"), automation: str = Form("ask"), note: str = Form("")):
    nickname = nickname.strip()
    if not nickname:
        raise HTTPException(400, "Nickname is required")
    with db.session() as c:
        if not c.execute("SELECT 1 FROM services WHERE id=?", (service_id,)).fetchone():
            raise HTTPException(400, "Unknown service")
        cur = c.execute(
            "INSERT INTO accounts(service_id, nickname, email, status, automation, note) "
            "VALUES (?,?,?,?,?,?)",
            (service_id, nickname, email.strip(), status, automation, note.strip()),
        )
        db.log(c, cur.lastrowid, "account_added", f"{nickname} ({service_id})")
    return back("/accounts")


@app.post("/accounts/{aid}/update")
def update_account(aid: int, status: str = Form(...), automation: str = Form(...)):
    with db.session() as c:
        c.execute("UPDATE accounts SET status=?, automation=? WHERE id=?", (status, automation, aid))
        db.log(c, aid, "account_updated", f"status={status}, automation={automation}")
    return back("/accounts")


@app.post("/accounts/{aid}/delete")
def delete_account(aid: int):
    with db.session() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (aid,))
        db.log(c, None, "account_deleted", str(aid))
    return back("/accounts")


# ---------- discount windows ----------
@app.post("/windows")
def create_window(account_id: int = Form(...), start_date: str = Form(...), weeks: int = Form(...),
                  label: str = Form(""), discount_value: float = Form(0)):
    start = parse_date(start_date, "Start date")
    if weeks < 1 or weeks > 52:
        raise HTTPException(400, "Weeks must be between 1 and 52")
    with db.session() as c:
        c.execute(
            "INSERT INTO windows(account_id, label, start_date, weeks, discount_value) VALUES (?,?,?,?,?)",
            (account_id, label.strip() or "Discount", start.isoformat(), weeks, discount_value),
        )
        db.log(c, account_id, "window_added", f"{weeks} weeks from {start}")
    return back("/accounts")


@app.post("/windows/{wid}/delete")
def delete_window(wid: int):
    with db.session() as c:
        c.execute("DELETE FROM windows WHERE id=?", (wid,))
    return back("/accounts")


# ---------- promo codes ----------
@app.get("/promos")
def promos_page(request: Request):
    with db.session() as c:
        st = load_state(c)
        rows = c.execute("SELECT * FROM promo_codes ORDER BY "
                         "CASE status WHEN 'available' THEN 0 WHEN 'reserved' THEN 1 ELSE 2 END, "
                         "COALESCE(expiry,'9999'), id").fetchall()
    soon = st["today"] + timedelta(days=14)
    return render(request, "promos.html", st=st, promos=rows, soon=soon.isoformat())


def promo_form_ctx(st, prefill=None, low=None, notes=None, candidates=None, raw=""):
    base = {"service": "", "code": "", "description": "", "discount_type": "percent",
            "discount_value": "", "weeks": "", "scope": "general", "account_id": "", "expiry": "",
            "source": "", "is_winback": False}
    base.update(prefill or {})
    return {"st": st, "p": base, "low": low or set(), "notes": notes or [],
            "candidates": candidates or [], "raw": raw}


@app.get("/promos/new")
def promo_new(request: Request):
    with db.session() as c:
        st = load_state(c)
    return render(request, "promo_form.html", **promo_form_ctx(st))


@app.get("/promos/scan")
def promo_scan_page(request: Request, error: str = ""):
    with db.session() as c:
        st = load_state(c)
    return render(request, "promo_scan.html", st=st, error=error)


@app.post("/promos/scan")
async def promo_scan(request: Request, photo: UploadFile = File(...)):
    data = await photo.read(ocr.MAX_BYTES + 1)
    with db.session() as c:
        st = load_state(c)
    try:
        text = ocr.ocr_image(data)
    except ocr.OcrUnavailable as exc:
        return render(request, "promo_scan.html", st=st, error=f"{exc} Enter the code by hand instead.")
    except ocr.OcrFailed as exc:
        return render(request, "promo_scan.html", st=st, error=str(exc))
    parsed = ocr.parse_promo_text(text)
    notes, low = [], set()
    if not parsed["code"]:
        notes.append("No code was found in the photo. Retake it closer and in good light, or type the code.")
        low.add("code")
    elif parsed["code_confidence"] < 0.8:
        notes.append("The code was found without a 'code' or 'promo' label. Check it carefully.")
        low.add("code")
    if not parsed["service"]:
        notes.append("The service was not recognised. Choose it below.")
        low.add("service")
    if not parsed["expiry"]:
        notes.append("No expiry date was found (or it was ambiguous).")
        low.add("expiry")
    if parsed["discount_value"] is None:
        low.add("discount_value")
    if parsed["weeks"] is None:
        low.add("weeks")
    prefill = {
        "service": parsed["service"] or "", "code": parsed["code"],
        "discount_type": parsed["discount_type"],
        "discount_value": "" if parsed["discount_value"] is None else parsed["discount_value"],
        "weeks": parsed["weeks"] or "", "expiry": parsed["expiry"], "source": "photo",
    }
    return render(request, "promo_form.html",
                  **promo_form_ctx(st, prefill, low, notes, parsed["candidates"], parsed["raw_text"]),
                  scanned=True)


@app.post("/promos")
def create_promo(service_id: str = Form(...), code: str = Form(...), description: str = Form(""),
                 discount_type: str = Form("percent"), discount_value: float = Form(0),
                 weeks: int = Form(1), scope: str = Form("general"), account_id: str = Form(""),
                 expiry: str = Form(""), source: str = Form(""), is_winback: Optional[str] = Form(None)):
    code = code.strip().upper()
    if not code:
        raise HTTPException(400, "Code is required")
    exp = parse_date(expiry, "Expiry", required=False)
    acct = int(account_id) if account_id.strip() else None
    if scope == "account" and acct is None:
        raise HTTPException(400, "Choose an account for an account-specific code")
    winback = bool(is_winback)
    if winback:
        scope = "account"
    with db.session() as c:
        status = "reserved" if scope == "account" else "available"
        c.execute(
            "INSERT INTO promo_codes(service_id, code, description, discount_type, discount_value, weeks, "
            "scope, account_id, expiry, source, is_winback, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (service_id, code, description.strip(), discount_type, discount_value, max(1, weeks), scope,
             acct if scope == "account" else None, exp.isoformat() if exp else None, source.strip(),
             int(winback), status),
        )
        db.log(c, acct, "promo_added", f"{code} ({service_id})")
    return back("/promos")


@app.post("/promos/{pid}/apply")
def apply_promo(pid: int, account_id: int = Form(...), start_date: str = Form(...)):
    start = parse_date(start_date, "Start date")
    with db.session() as c:
        p = c.execute("SELECT * FROM promo_codes WHERE id=?", (pid,)).fetchone()
        a = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not p or not a:
            raise HTTPException(404, "Code or account not found")
        if p["status"] not in ("available", "reserved"):
            raise HTTPException(400, f"This code is {p['status']}")
        if p["service_id"] != a["service_id"]:
            raise HTTPException(400, "The code and the account are on different services")
        if p["scope"] == "account" and p["account_id"] != account_id:
            raise HTTPException(400, "This code is tied to a different account")
        c.execute(
            "INSERT INTO windows(account_id, code_id, label, start_date, weeks, discount_value) "
            "VALUES (?,?,?,?,?,?)",
            (account_id, pid, p["code"], start.isoformat(), p["weeks"], p["discount_value"]),
        )
        c.execute("UPDATE promo_codes SET status='applied', account_id=? WHERE id=?", (account_id, pid))
        db.log(c, account_id, "promo_applied", f"{p['code']} from {start}")
    return back("/")


@app.post("/promos/{pid}/delete")
def delete_promo(pid: int):
    with db.session() as c:
        c.execute("DELETE FROM promo_codes WHERE id=?", (pid,))
    return back("/promos")


# ---------- overrides ----------
@app.post("/overrides")
def create_override(week_start: str = Form(...), kind: str = Form(...), account_id: str = Form("")):
    wk = sch.monday(parse_date(week_start, "Week"))
    if kind not in ("force", "block", "empty"):
        raise HTTPException(400, "Unknown override")
    acct = int(account_id) if account_id.strip() else None
    if kind != "empty" and acct is None:
        raise HTTPException(400, "Choose an account")
    with db.session() as c:
        c.execute("INSERT INTO overrides(week_start, kind, account_id) VALUES (?,?,?)",
                  (wk.isoformat(), kind, acct if kind != "empty" else None))
        db.log(c, acct, "override_added", f"{kind} for week of {wk}")
    return back("/")


@app.post("/overrides/{oid}/delete")
def delete_override(oid: int):
    with db.session() as c:
        c.execute("DELETE FROM overrides WHERE id=?", (oid,))
    return back("/")


# ---------- action queue ----------
@app.get("/actions")
def actions_page(request: Request):
    with db.session() as c:
        st = load_state(c)
    return render(request, "actions.html", st=st, actions=st["actions"],
                  horizon_limit=(st["today"] + timedelta(days=21)))


@app.post("/actions/done")
def action_done(type: str = Form(...), account_id: int = Form(...), week: str = Form(...)):
    wk = parse_date(week, "Week")
    key = f"{type}:{account_id}:{wk.isoformat()}"
    with db.session() as c:
        if type == "reactivate":
            c.execute("UPDATE accounts SET status='active' WHERE id=?", (account_id,))
        elif type == "cancel":
            planned = c.execute(
                "SELECT 1 FROM plan WHERE week_start=? AND account_id=? AND state='delivering'",
                (wk.isoformat(), account_id),
            ).fetchone()
            c.execute("UPDATE accounts SET status='cancelled' WHERE id=?", (account_id,))
            if planned:  # the box for this week is already locked in, keep it in the plan
                c.execute("INSERT INTO overrides(week_start, kind, account_id, committed) "
                          "VALUES (?, 'force', ?, 1)", (wk.isoformat(), account_id))
        elif type != "skip":
            raise HTTPException(400, "Unknown action")
        c.execute("INSERT OR IGNORE INTO actions_done(key) VALUES (?)", (key,))
        db.log(c, account_id, f"{type}_done", f"week of {wk}")
    return back("/actions")


# ---------- settings ----------
@app.get("/settings")
def settings_page(request: Request):
    with db.session() as c:
        st = load_state(c)
        log_rows = c.execute(
            "SELECT e.ts, e.event, e.detail, a.nickname FROM event_log e "
            "LEFT JOIN accounts a ON a.id = e.account_id ORDER BY e.id DESC LIMIT 25").fetchall()
    return render(request, "settings.html", st=st, log=log_rows)


@app.post("/settings")
def save_settings(horizon_weeks: int = Form(12)):
    with db.session() as c:
        db.set_setting(c, "horizon_weeks", str(max(1, min(52, horizon_weeks))))
    return back("/settings")


@app.post("/services/{sid}")
def update_service(sid: str, skip_cutoff_days: int = Form(...), reactivate_lead_days: int = Form(...),
                   skips_consume_window: Optional[str] = Form(None)):
    with db.session() as c:
        c.execute(
            "UPDATE services SET skip_cutoff_days=?, reactivate_lead_days=?, skips_consume_window=? WHERE id=?",
            (max(0, skip_cutoff_days), max(0, reactivate_lead_days), int(bool(skips_consume_window)), sid),
        )
    return back("/settings")
