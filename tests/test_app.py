import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config, ocr
from app import main as main_mod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr(config, "today", lambda: date(2026, 10, 7))
    with TestClient(main_mod.app) as c:
        yield c


def add_account(client, nick, service="hellofresh", status="active"):
    r = client.post("/accounts", data={"service_id": service, "nickname": nick, "status": status},
                    follow_redirects=False)
    assert r.status_code == 303


def test_health_and_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["version"] == config.version()


def test_pages_render_empty(client):
    for path in ["/", "/accounts", "/promos", "/promos/new", "/promos/scan", "/actions", "/settings"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "Meal Kit Manager v" in r.text


def test_full_flow_code_to_plan(client):
    add_account(client, "HF main", "hellofresh")
    add_account(client, "CP spare", "chefsplate", status="cancelled")
    r = client.post("/promos", data={"service_id": "hellofresh", "code": "save60", "discount_type": "percent",
                                     "discount_value": "60", "weeks": "3", "scope": "general"},
                    follow_redirects=False)
    assert r.status_code == 303
    r = client.post("/promos/1/apply", data={"account_id": "1", "start_date": "2026-10-05"},
                    follow_redirects=False)
    assert r.status_code == 303
    # a win-back code is tied to the cancelled account
    client.post("/promos", data={"service_id": "chefsplate", "code": "COMEBACK", "weeks": "2", "is_winback": "1",
                                 "account_id": "2", "discount_value": "50"})
    client.post("/promos/2/apply", data={"account_id": "2", "start_date": "2026-11-02"})

    plan = client.get("/api/plan").json()
    delivering = [w["delivering"] for w in plan["weeks"]][:6]
    assert delivering == [1, 1, 1, None, 2, 2]  # CP waits (cancelled) until its window
    types = {(a["type"], a["account_id"]) for a in plan["actions"]}
    assert ("cancel", 1) in types and ("reactivate", 2) in types

    page = client.get("/")
    assert "Delivering" in page.text and "Waiting" in page.text

    # applying the same code twice is refused
    assert client.post("/promos/1/apply", data={"account_id": "1", "start_date": "2026-10-05"}).status_code == 400


def test_marking_cancel_done_keeps_locked_box(client):
    add_account(client, "HF main")
    client.post("/promos", data={"service_id": "hellofresh", "code": "ONEBOX", "weeks": "1"})
    client.post("/promos/1/apply", data={"account_id": "1", "start_date": "2026-10-05"})
    plan = client.get("/api/plan").json()
    cancel = [a for a in plan["actions"] if a["type"] == "cancel"][0]
    client.post("/actions/done", data={"type": "cancel", "account_id": "1", "week": cancel["week"]})
    plan = client.get("/api/plan").json()
    assert plan["weeks"][0]["delivering"] == 1  # the order already locked in still counts
    assert not [a for a in plan["actions"] if a["type"] == "cancel"]


def test_scan_prefills_form(client, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_image",
                        lambda data: "HelloFresh\n50% off 3 boxes\nUse code FALL50\nExpires 2026-12-01")
    r = client.post("/promos/scan", files={"photo": ("p.jpg", io.BytesIO(b"x"), "image/jpeg")})
    assert r.status_code == 200
    assert 'value="FALL50"' in r.text and "2026-12-01" in r.text
    assert "Confirm the scanned code" in r.text
    # nothing is saved until the form is submitted
    assert "FALL50" not in client.get("/promos").text


def test_scan_reports_missing_engine(client, monkeypatch):
    def boom(_):
        raise ocr.OcrUnavailable("The Tesseract engine is not installed on this server.")
    monkeypatch.setattr(ocr, "ocr_image", boom)
    r = client.post("/promos/scan", files={"photo": ("p.jpg", io.BytesIO(b"x"), "image/jpeg")})
    assert r.status_code == 200 and "Tesseract" in r.text


def test_scan_rejects_non_image(client):
    r = client.post("/promos/scan", files={"photo": ("p.txt", io.BytesIO(b"not an image"), "text/plain")})
    assert r.status_code == 200
    assert "could not be read as an image" in r.text or "not installed" in r.text


def test_password_protection(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    assert client.get("/").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/", auth=("me", "wrong")).status_code == 401
    assert client.get("/", auth=("me", "s3cret")).status_code == 200


def test_past_weeks_count_as_delivered(client, monkeypatch):
    add_account(client, "HF main")
    client.post("/promos", data={"service_id": "hellofresh", "code": "FOURBOX", "weeks": "4"})
    client.post("/promos/1/apply", data={"account_id": "1", "start_date": "2026-10-05"})
    client.get("/")  # stores the plan
    monkeypatch.setattr(config, "today", lambda: date(2026, 10, 7) + timedelta(days=14))
    plan = client.get("/api/plan").json()
    # two boxes (Oct 5, Oct 12) are now history, two remain from Oct 19
    assert [w["delivering"] for w in plan["weeks"]][:3] == [1, 1, None]
