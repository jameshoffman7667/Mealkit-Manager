from datetime import date

from app.connectors import parse

TODAY = date(2026, 10, 7)


def test_find_date_infers_year():
    assert parse.find_date("Delivery Mon, Oct 12", TODAY) == date(2026, 10, 12)
    assert parse.find_date("Arrives January 4", TODAY) == date(2027, 1, 4)   # next year
    assert parse.find_date("Arrives Sept. 30th, 2026", TODAY) == date(2026, 9, 30)
    assert parse.find_date("market 5 items", TODAY) is None                  # not a month


def test_parse_card_states():
    assert parse.parse_card("Oct 12\nSkipped\nUnskip", TODAY) == (date(2026, 10, 12), "skipped")
    assert parse.parse_card("Wed, Oct 14\nDelivery scheduled\nSkip this week", TODAY) == (date(2026, 10, 12), "delivering")
    assert parse.parse_card("Oct 19 Paused", TODAY) == (date(2026, 10, 19), "paused")
    assert parse.parse_card("Order cancelled Oct 26", TODAY) == (date(2026, 10, 26), "skipped")
    assert parse.parse_card("No dates here, skip", TODAY) is None


def test_parse_account_status():
    assert parse.parse_account_status("Your plan: 3 meals per week, 2 servings") == "active"
    assert parse.parse_account_status("Your plan is paused. Resume") == "paused"
    assert parse.parse_account_status("Welcome back! Reactivate your plan") == "cancelled"
    assert parse.parse_account_status("Something unrelated") is None


def test_verification_and_payment_detection():
    assert parse.detect_verification("Please enter the code we sent")
    assert parse.detect_verification("Are you a robot?")
    assert not parse.detect_verification("Your upcoming deliveries")
    assert "payment" in parse.detect_payment_issue("Your payment failed on Oct 3").lower()
    assert parse.detect_payment_issue("All good") == ""
