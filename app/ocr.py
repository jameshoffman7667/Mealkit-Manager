"""Promo code recognition from a photo.

Text recognition uses Tesseract (installed in the Docker image). The parsing step
is plain Python and is tested without Tesseract.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Optional

MAX_BYTES = 10 * 1024 * 1024

SERVICE_PATTERNS = {
    "hellofresh": [r"hello\s*fresh"],
    "chefsplate": [r"chef'?s?\s*plate", r"chefsplate"],
    "goodfood": [r"good\s*food", r"goodfood"],
}

STOP_WORDS = {
    "HELLOFRESH", "CHEFSPLATE", "GOODFOOD", "DISCOUNT", "PROMO", "COUPON", "EXPIRES",
    "FRESH", "WELCOME", "SUBSCRIPTION", "DELIVERY", "SHIPPING", "REDEEM", "ONLINE",
    "OFFER", "LIMITED", "VALID", "BOXES", "TERMS", "APPLY", "APPLIES", "CUSTOMERS",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class OcrUnavailable(RuntimeError):
    """Raised when the OCR engine or image library is missing."""


class OcrFailed(RuntimeError):
    """Raised when the uploaded file cannot be read as an image."""


def guess_service(text: str) -> Optional[str]:
    low = text.lower()
    for sid, pats in SERVICE_PATTERNS.items():
        if any(re.search(p, low) for p in pats):
            return sid
    return None


def find_expiry(text: str) -> Optional[date]:
    t = text.replace(",", " ")
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", t)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(20\d{2})\b", t)
    if m and m[1][:3].lower() in MONTHS:
        try:
            return date(int(m[3]), MONTHS[m[1][:3].lower()], int(m[2]))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(20\d{2})\b", t)
    if m and m[2][:3].lower() in MONTHS:
        try:
            return date(int(m[3]), MONTHS[m[2][:3].lower()], int(m[1]))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b", t)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a > 12 >= b:
            day, month = a, b
        elif b > 12 >= a:
            month, day = a, b
        else:
            return None  # e.g. 03/04/2027 is ambiguous: leave blank for the user
        try:
            return date(y, month, day)
        except ValueError:
            return None
    return None


def find_discount(text: str) -> tuple:
    m = re.search(r"(\d{1,3})\s*%\s*off", text, re.I)
    if m:
        return "percent", float(m[1])
    m = re.search(r"\$\s*(\d{1,3}(?:\.\d{2})?)\s*off", text, re.I)
    if m:
        return "fixed", float(m[1])
    m = re.search(r"(\d{1,3})\s*%", text)
    if m:
        return "percent", float(m[1])
    return None, None


def find_weeks(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{1,2})\s*(?:weeks?|boxes|deliveries)\b", text, re.I)
    if m and 1 <= int(m[1]) <= 52:
        return int(m[1])
    return None


def find_code_candidates(text: str) -> list:
    """Return [(code, confidence)] best first."""
    found: dict = {}

    def add(code: str, conf: float) -> None:
        code = code.strip("-").upper()
        if len(code) < 4 or code in STOP_WORDS:
            return
        found[code] = max(found.get(code, 0), conf)

    for m in re.finditer(r"(?i:code|promo|coupon|use)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-]{3,19})\b", text):
        add(m[1], 0.9)
    for tok in re.findall(r"\b[A-Z0-9][A-Z0-9\-]{4,19}\b", text):
        has_d = any(ch.isdigit() for ch in tok)
        has_a = any(ch.isalpha() for ch in tok)
        if has_d and has_a:
            add(tok, 0.6)
        elif has_a and len(tok) >= 6:
            add(tok, 0.4)
    return sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))


def parse_promo_text(text: str) -> dict:
    cands = find_code_candidates(text)
    dtype, dval = find_discount(text)
    expiry = find_expiry(text)
    weeks = find_weeks(text)
    service = guess_service(text)
    return {
        "service": service,
        "code": cands[0][0] if cands else "",
        "code_confidence": cands[0][1] if cands else 0.0,
        "candidates": [c for c, _ in cands[:6]],
        "discount_type": dtype or "percent",
        "discount_value": dval,
        "weeks": weeks,
        "expiry": expiry.isoformat() if expiry else "",
        "raw_text": text.strip(),
    }


def ocr_image(data: bytes) -> str:
    """Read text from image bytes. The image is never written to disk."""
    if len(data) > MAX_BYTES:
        raise OcrFailed("The photo is larger than 10 MB.")
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError as exc:  # pragma: no cover
        raise OcrUnavailable("Text recognition libraries are not installed.") from exc
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = ImageOps.autocontrast(img.convert("L"))
    except Exception as exc:
        raise OcrFailed("That file could not be read as an image.") from exc
    if max(img.size) < 1400:
        scale = 1400 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    try:
        texts = [pytesseract.image_to_string(img, config="--psm 6")]
        if not find_code_candidates(texts[0]):
            texts.append(pytesseract.image_to_string(img, config="--psm 11"))
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailable("The Tesseract engine is not installed on this server.") from exc
    except Exception as exc:  # pragma: no cover
        raise OcrFailed("Text recognition failed on this photo.") from exc
    return "\n".join(texts)
