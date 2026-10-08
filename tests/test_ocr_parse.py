from app import ocr


def test_hellofresh_flyer():
    text = "HELLOFRESH\nGet 60% off your next 4 boxes\nUse code WELCOME4ME at checkout\nExpires Dec 31, 2026"
    p = ocr.parse_promo_text(text)
    assert p["service"] == "hellofresh"
    assert p["code"] == "WELCOME4ME"
    assert p["discount_type"] == "percent" and p["discount_value"] == 60
    assert p["weeks"] == 4
    assert p["expiry"] == "2026-12-31"
    assert p["code_confidence"] >= 0.9


def test_chefs_plate_fixed_amount_and_iso_date():
    text = "Chef's Plate\n$80 off\nPromo code: CP-SAVE80\nvalid until 2027-01-15"
    p = ocr.parse_promo_text(text)
    assert p["service"] == "chefsplate"
    assert p["code"] == "CP-SAVE80"
    assert p["discount_type"] == "fixed" and p["discount_value"] == 80
    assert p["expiry"] == "2027-01-15"


def test_goodfood_without_label_gives_lower_confidence():
    p = ocr.parse_promo_text("Good Food\nBRINGITBACK25\nbig savings")
    assert p["service"] == "goodfood"
    assert p["code"] == "BRINGITBACK25"
    assert p["code_confidence"] < 0.9


def test_ambiguous_numeric_date_is_left_blank():
    assert ocr.find_expiry("expires 03/04/2027") is None
    assert ocr.find_expiry("expires 25/04/2027").isoformat() == "2027-04-25"
    assert ocr.find_expiry("expires 04/25/2027").isoformat() == "2027-04-25"


def test_no_code_found():
    p = ocr.parse_promo_text("nothing useful here, just words")
    assert p["code"] == "" and p["candidates"] == []


def test_stop_words_are_not_codes():
    cands = [c for c, _ in ocr.find_code_candidates("HELLOFRESH DISCOUNT WELCOME")]
    assert cands == []
