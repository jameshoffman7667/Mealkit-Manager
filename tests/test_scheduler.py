from datetime import date, timedelta

from app.scheduler import Acct, Ovr, Svc, Win, build_plan, monday

TODAY = date(2026, 10, 7)  # a Wednesday
WK0 = monday(TODAY)  # Mon Oct 5
SERVICES = {
    "hf": Svc("hf", "HelloFresh"),
    "cp": Svc("cp", "Chef's Plate"),
}


def wk(n):
    return WK0 + timedelta(days=7 * n)


def seq(plan):
    return [w.delivering for w in plan.weeks]


def test_one_delivery_per_week_and_soonest_expiring_first():
    accounts = [Acct(1, "hf", "A"), Acct(2, "cp", "B")]
    windows = [Win(10, 1, wk(0), 3), Win(11, 2, wk(0), 2)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=8)
    assert seq(plan) == [2, 2, 1, 1, 1, None, None, None]
    assert plan.covered == 5
    assert len(plan.gaps) == 3
    for w in plan.weeks:
        assert sum(c.state == "delivering" for c in w.cells.values()) <= 1


def test_non_delivering_live_accounts_are_skipped():
    accounts = [Acct(1, "hf", "A"), Acct(2, "cp", "B")]
    windows = [Win(10, 1, wk(0), 3), Win(11, 2, wk(0), 2)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=4)
    assert plan.weeks[0].cells[1].state == "skipped"
    assert plan.weeks[0].cells[2].state == "delivering"
    skips = {(a.account_id, a.week) for a in plan.actions if a.type == "skip"}
    # week 0 is locked (cut-off passed), so no skip action for it
    assert (1, wk(0)) not in skips
    assert (1, wk(1)) in skips
    assert plan.weeks[0].cells[1].locked


def test_cancel_after_last_discounted_box():
    accounts = [Acct(1, "hf", "A"), Acct(2, "cp", "B")]
    windows = [Win(10, 1, wk(0), 3), Win(11, 2, wk(0), 2)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=8)
    cancels = {a.account_id: a for a in plan.actions if a.type == "cancel"}
    assert cancels[2].week == wk(1)
    assert cancels[1].week == wk(4)
    assert cancels[1].due == wk(4)
    # after cancelling, the account is no longer skipped, it is inactive
    assert plan.weeks[5].cells[1].state == "inactive"
    assert plan.weeks[3].cells[2].state == "inactive"


def test_reactivation_planned_before_first_box_and_waiting_before():
    accounts = [Acct(1, "hf", "A", status="cancelled")]
    windows = [Win(10, 1, wk(4), 3)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=10)
    assert plan.weeks[0].cells[1].state == "waiting"
    assert seq(plan)[4:7] == [1, 1, 1]
    react = [a for a in plan.actions if a.type == "reactivate"]
    assert len(react) == 1
    assert react[0].due == wk(4) - timedelta(days=10)
    assert react[0].week == wk(4)


def test_late_reactivation_is_flagged():
    accounts = [Acct(1, "hf", "A", status="cancelled")]
    windows = [Win(10, 1, wk(0), 2)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=3)
    react = [a for a in plan.actions if a.type == "reactivate"][0]
    assert react.due == TODAY
    assert "Late" in react.note


def test_active_account_without_discount_is_at_risk_and_cancelled():
    accounts = [Acct(1, "hf", "A")]
    plan = build_plan(TODAY, accounts, SERVICES, [], [], horizon=3)
    assert plan.weeks[0].cells[1].state == "at_risk"
    assert plan.weeks[1].cells[1].state == "inactive"
    cancel = [a for a in plan.actions if a.type == "cancel"][0]
    assert cancel.due == TODAY


def test_boxes_used_in_the_past_reduce_the_window():
    accounts = [Acct(1, "hf", "A")]
    windows = [Win(10, 1, wk(-2), 4, used=3)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, [], horizon=3)
    assert seq(plan) == [1, None, None]
    assert plan.window_ends[10] == wk(0) + timedelta(days=6)


def test_time_based_window_is_used_up_by_the_calendar():
    services = {"hf": Svc("hf", skips_consume_window=True), "cp": Svc("cp", skips_consume_window=True)}
    accounts = [Acct(1, "hf", "A"), Acct(2, "cp", "B")]
    windows = [Win(10, 1, wk(0), 3), Win(11, 2, wk(0), 2)]
    plan = build_plan(TODAY, accounts, services, windows, [], horizon=5)
    # B expires first so it delivers weeks 0-1; A's weeks 0-1 are skipped and burned
    assert seq(plan) == [2, 2, 1, None, None]
    assert plan.window_ends[10] == wk(2) + timedelta(days=6)


def test_overrides_empty_block_force():
    accounts = [Acct(1, "hf", "A"), Acct(2, "cp", "B")]
    windows = [Win(10, 1, wk(0), 5), Win(11, 2, wk(0), 5)]
    ovr = [Ovr(wk(1), "empty"), Ovr(wk(2), "block", 2), Ovr(wk(3), "force", 2)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, ovr, horizon=5)
    s = seq(plan)
    assert s[1] is None and plan.weeks[1].empty and wk(1) not in plan.gaps
    assert s[2] == 1
    assert plan.weeks[2].cells[2].reason == "Blocked by you"
    assert s[3] == 2


def test_forced_box_without_discount_is_flagged_full_price():
    accounts = [Acct(1, "hf", "A")]
    ovr = [Ovr(wk(2), "force", 1)]
    plan = build_plan(TODAY, accounts, SERVICES, [], ovr, horizon=4)
    cell = plan.weeks[2].cells[1]
    assert cell.state == "delivering" and cell.full_price


def test_committed_box_does_not_trigger_reactivation():
    accounts = [Acct(1, "hf", "A", status="cancelled")]
    windows = [Win(10, 1, wk(0), 1)]
    ovr = [Ovr(wk(0), "force", 1, committed=True)]
    plan = build_plan(TODAY, accounts, SERVICES, windows, ovr, horizon=3)
    assert plan.weeks[0].delivering == 1
    assert not [a for a in plan.actions if a.type in ("reactivate", "cancel")]


def test_service_cutoff_controls_locking():
    services = {"hf": Svc("hf", skip_cutoff_days=12)}
    accounts = [Acct(1, "hf", "A"), Acct(2, "hf", "B")]
    windows = [Win(10, 1, wk(0), 5), Win(11, 2, wk(0), 5)]
    plan = build_plan(TODAY, accounts, services, windows, [], horizon=4)
    assert plan.weeks[1].cells[2].locked  # wk1 - 12 days is before today
    assert not plan.weeks[3].cells[2].locked
