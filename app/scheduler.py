"""Week assignment engine (pure functions, no database access).

Rules, in priority order (see FUNCTIONAL_SPEC.md section 5.2):
  1. One delivery per week across all accounts.
  2. Only accounts with a usable discount window can deliver.
  3. Every live account that is not delivering is skipped.
  4. An account with no discounted weeks left is cancelled after its last box.
  5. Prefer the account whose discount runs out soonest.
  6. Weeks with no eligible discount stay empty (gap) unless the user forces a box.
  7. Weeks inside a service's skip cut-off are locked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass
class Svc:
    id: str
    name: str = ""
    skip_cutoff_days: int = 5
    reactivate_lead_days: int = 10
    # False: the discount covers N delivered boxes. True: it covers N calendar weeks.
    skips_consume_window: bool = False


@dataclass
class Acct:
    id: int
    service_id: str
    nickname: str
    status: str = "active"  # active | cancelled | paused


@dataclass
class Win:
    id: int
    account_id: int
    start: date
    weeks: int
    used: int = 0
    value: float = 0.0
    label: str = ""


@dataclass
class Ovr:
    week: date
    kind: str  # force | block | empty
    account_id: Optional[int] = None
    committed: bool = False  # order already locked after a cancel was marked done


@dataclass
class Cell:
    state: str  # delivering | skipped | inactive | waiting | at_risk
    reason: str = ""
    locked: bool = False
    full_price: bool = False
    window_id: Optional[int] = None


@dataclass
class Week:
    start: date
    delivering: Optional[int] = None
    empty: bool = False
    cells: dict = field(default_factory=dict)


@dataclass
class Action:
    type: str  # skip | reactivate | cancel
    account_id: int
    due: date
    week: date
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.type}:{self.account_id}:{self.week.isoformat()}"


@dataclass
class Plan:
    weeks: list
    actions: list
    window_ends: dict  # window id -> last covered date, or None if beyond the horizon
    gaps: list  # week starts with no delivery and no empty override

    @property
    def covered(self) -> int:
        return sum(1 for w in self.weeks if w.delivering is not None)


def build_plan(
    today: date,
    accounts: list,
    services: dict,
    windows: list,
    overrides: list,
    horizon: int = 12,
) -> Plan:
    wk0 = monday(today)
    wks = [wk0 + timedelta(days=7 * i) for i in range(horizon)]
    acc = {a.id: a for a in accounts}

    def svc(aid) -> Svc:
        return services.get(acc[aid].service_id) or Svc(acc[aid].service_id)

    wins = {
        a.id: sorted((w for w in windows if w.account_id == a.id), key=lambda w: (w.start, w.id))
        for a in accounts
    }
    boxes = {w.id: max(0, w.weeks - w.used) for w in windows}
    live = {a.id: a.status == "active" for a in accounts}
    live_until: dict = {}
    win_last: dict = {}

    def last_week(w: Win) -> date:
        return monday(w.start) + timedelta(days=7 * (w.weeks - 1))

    def usable(aid, w: Win, wk: date) -> bool:
        if wk < monday(w.start):
            return False
        if svc(aid).skips_consume_window:
            return wk <= last_week(w)
        return boxes[w.id] > 0

    def pick(aid, wk: date) -> Optional[Win]:
        for w in wins[aid]:
            if usable(aid, w, wk):
                return w
        return None

    def capacity(aid, frm: date) -> bool:
        for w in wins[aid]:
            if svc(aid).skips_consume_window:
                if last_week(w) >= frm:
                    return True
            elif boxes[w.id] > 0:
                return True
        return False

    def est_end(aid, w: Win, wk: date) -> date:
        if svc(aid).skips_consume_window:
            return last_week(w)
        return wk + timedelta(days=7 * boxes[w.id])

    def locked(aid, wk: date) -> bool:
        return (wk - timedelta(days=svc(aid).skip_cutoff_days)) < today

    ovr = [
        Ovr(monday(o.week), o.kind, o.account_id, o.committed)
        for o in overrides
        if o.kind == "empty" or o.account_id in acc
    ]

    actions: list = []
    at_risk_start: set = set()
    for a in accounts:
        if live[a.id] and not capacity(a.id, wk0):
            at_risk_start.add(a.id)
            live[a.id] = False
            live_until[a.id] = 0
            actions.append(Action("cancel", a.id, today, wk0, "No discounted weeks left"))

    weeks: list = []
    gaps: list = []
    for i, wk in enumerate(wks):
        week = Week(wk)
        week.empty = any(o.kind == "empty" and o.week == wk for o in ovr)
        blocked = {o.account_id for o in ovr if o.kind == "block" and o.week == wk}
        forced = [o for o in ovr if o.kind == "force" and o.week == wk]

        chosen = None
        chosen_win: Optional[Win] = None
        committed = False
        why = ""
        if forced:
            chosen = forced[0].account_id
            committed = forced[0].committed
            chosen_win = pick(chosen, wk)
            why = "Order already locked" if committed else "Forced by you"
        elif not week.empty:
            cands = []
            for a in accounts:
                if a.id in blocked:
                    continue
                w = pick(a.id, wk)
                if w:
                    cands.append((est_end(a.id, w, wk), -w.value, a.nickname.lower(), a.id, w))
            if cands:
                cands.sort(key=lambda t: t[:4])
                chosen, chosen_win = cands[0][3], cands[0][4]
                why = "Soonest-expiring discount"

        if chosen is not None:
            week.delivering = chosen
            if not live[chosen] and not committed:
                due = wk - timedelta(days=svc(chosen).reactivate_lead_days)
                note = ""
                if due < today:
                    due = today
                    note = "Late: reactivate now, this box may not ship in time"
                actions.append(Action("reactivate", chosen, due, wk, note))
                live[chosen] = True
            full = chosen_win is None
            if chosen_win is not None:
                win_last[chosen_win.id] = wk
                if not svc(chosen).skips_consume_window:
                    boxes[chosen_win.id] -= 1
            label = chosen_win.label if chosen_win and chosen_win.label else "discount"
            week.cells[chosen] = Cell(
                "delivering",
                f"{label}" if not full else "No discount covers this box",
                locked(chosen, wk),
                full,
                chosen_win.id if chosen_win else None,
            )
            if not committed and not capacity(chosen, wk + timedelta(days=7)):
                actions.append(Action("cancel", chosen, max(today, wk), wk, "Last discounted box"))
                live[chosen] = False
                live_until[chosen] = i
        elif not week.empty:
            gaps.append(wk)

        for a in accounts:
            if a.id == chosen:
                continue
            is_live = live[a.id] or live_until.get(a.id, -1) >= i
            cap = capacity(a.id, wk)
            if is_live:
                if a.id in at_risk_start and i == 0:
                    week.cells[a.id] = Cell("at_risk", "No discount left, cancel queued")
                    continue
                if a.id in blocked:
                    reason = "Blocked by you"
                elif week.empty:
                    reason = "Week left empty by you"
                elif chosen is not None:
                    reason = f"{acc[chosen].nickname} delivers"
                else:
                    reason = "No discount this week"
                lk = locked(a.id, wk)
                week.cells[a.id] = Cell("skipped", reason, lk)
                if not lk:
                    deadline = wk - timedelta(days=svc(a.id).skip_cutoff_days)
                    actions.append(Action("skip", a.id, max(today, deadline), wk))
            else:
                week.cells[a.id] = Cell("waiting" if cap else "inactive")
        weeks.append(week)

    ends: dict = {}
    for w in windows:
        if svc(w.account_id).skips_consume_window:
            ends[w.id] = last_week(w) + timedelta(days=6)
        elif boxes[w.id] <= 0 and w.id in win_last:
            ends[w.id] = win_last[w.id] + timedelta(days=6)
        else:
            ends[w.id] = None
    actions.sort(key=lambda x: (x.due, x.type != "cancel", x.account_id))
    return Plan(weeks, actions, ends, gaps)
