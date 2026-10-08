"""Turns page text from a service site into plain facts. Pure functions, easy to test."""
import re
from datetime import date, timedelta
from typing import Optional

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "oct": 10, "nov": 11, "dec": 12}
DATE_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(\d{4}))?\b", re.I)

VERIFY_MARKERS = (
    "verification code", "verify your", "captcha", "are you a human", "are you a robot",
    "security check", "one-time", "two-factor", "2-step", "check your email", "enter the code",
    "unusual activity", "confirm it's you", "confirm it’s you",
)
PAYMENT_RE = re.compile(
    r"(payment (has )?(failed|declined)|update (your )?payment|past due|unpaid|outstanding balance|payment issue)", re.I)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def find_date(text: str, today: date) -> Optional[date]:
    m = DATE_RE.search(text)
    if not m:
        return None
    month = MONTHS[m.group(1)[:3].lower()]
    day = int(m.group(2))
    try:
        if m.group(3):
            return date(int(m.group(3)), month, day)
        d = date(today.year, month, day)
        if d < today - timedelta(days=90):
            d = date(today.year + 1, month, day)
        return d
    except ValueError:
        return None


def parse_card(text: str, today: date):
    """One delivery card -> (Monday of its week, state) or None if it is not recognisable."""
    low = text.lower()
    d = find_date(text, today)
    if d is None:
        return None
    if re.search(r"\bskipped\b|\bcancell?ed\b", low):
        state = "skipped"
    elif re.search(r"\bpaused\b", low):
        state = "paused"
    elif re.search(r"deliver|arriv|ship|schedul|order|skip|edit|modify|meals", low):
        state = "delivering"
    else:
        return None
    return monday(d), state


def parse_account_status(text: str) -> Optional[str]:
    low = text.lower()
    if re.search(r"(plan|subscription|account)\s+(is|has been|was)\s+cancell?ed|reactivate|"
                 r"restart (your )?(plan|subscription)|welcome back|come back", low):
        return "cancelled"
    if re.search(r"\bpaused\b|\bresume\b", low):
        return "paused"
    if re.search(r"meals? per week|servings|your plan|next delivery|upcoming deliver|manage (your )?plan", low):
        return "active"
    return None


def detect_verification(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in VERIFY_MARKERS)


def detect_payment_issue(text: str) -> str:
    m = PAYMENT_RE.search(text)
    return m.group(0) if m else ""
