"""Deterministic validation + normalisation. No LLM is ever used here."""
import re
from datetime import date, datetime
from typing import Optional, Tuple

from .textnorm import normalize_text

MONTHS = {
    1: ["january", "jan", "janwari", "january", "جنوری"],
    2: ["february", "feb", "farwari", "fervari", "فروری"],
    3: ["march", "mar", "maarch", "مارچ"],
    4: ["april", "apr", "aprail", "apreil", "اپریل"],
    5: ["may", "mai", "مئی", "مئ"],
    6: ["june", "jun", "جون"],
    7: ["july", "jul", "julai", "جولائی"],
    8: ["august", "aug", "agast", "اگست"],
    9: ["september", "sep", "sept", "sitambar", "ستمبر"],
    10: ["october", "oct", "aktubar", "اکتوبر"],
    11: ["november", "nov", "navambar", "نومبر"],
    12: ["december", "dec", "disambar", "دسمبر"],
}
MONTH_LOOKUP = {name: num for num, names in MONTHS.items() for name in names}
_MONTH_RE = "|".join(sorted((re.escape(m) for m in MONTH_LOOKUP), key=len, reverse=True))

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")

_DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"), "ymd"),
    (re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)"), "dmy"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_MONTH_RE})[,\s]+(\d{{4}})(?!\d)", re.I), "d-mon-y"),
    (re.compile(rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,\s]+(\d{{4}})(?!\d)", re.I), "mon-d-y"),
]


def _mk_date(y: int, m: int, d: int) -> Optional[str]:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def find_dates(text: str) -> list:
    """Return every date found in text as ISO strings (YYYY-MM-DD). Pakistan style = day first."""
    text = normalize_text(text)
    found = []
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            if kind == "ymd":
                iso = _mk_date(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "dmy":
                iso = _mk_date(int(g[2]), int(g[1]), int(g[0]))
            elif kind == "d-mon-y":
                iso = _mk_date(int(g[2]), MONTH_LOOKUP[g[1].lower()], int(g[0]))
            else:
                iso = _mk_date(int(g[2]), MONTH_LOOKUP[g[0].lower()], int(g[1]))
            if iso and iso not in found:
                found.append(iso)
    return found


def norm_cnic(v: str) -> Optional[str]:
    d = re.sub(r"\D", "", normalize_text(v))
    return f"{d[:5]}-{d[5:12]}-{d[12]}" if len(d) == 13 else None


def norm_phone(v: str) -> Optional[str]:
    d = re.sub(r"\D", "", normalize_text(v))
    if d.startswith("0092"):
        d = "0" + d[4:]
    elif d.startswith("92") and len(d) == 12:
        d = "0" + d[2:]
    elif len(d) == 10 and d.startswith("3"):
        d = "0" + d
    return f"{d[:4]}-{d[4:]}" if len(d) == 11 and d.startswith("03") else None


def norm_email(v: str) -> Optional[str]:
    v = re.sub(r"\s+", "", normalize_text(v)).lower()
    return v if EMAIL_RE.match(v) else None


def norm_date(v: str) -> Optional[str]:
    v = (v or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            return None
    dates = find_dates(v)
    return dates[0] if dates else None


def norm_number(v: str) -> Optional[str]:
    v = normalize_text(v).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", v)
    return m.group(0) if m else None


def match_option(value: str, options: list) -> Optional[str]:
    v = (value or "").strip().lower()
    if not v:
        return None
    for o in options:
        if o.lower() == v:
            return o
    for o in options:  # loose containment either way ("bachelor" -> "Bachelor's")
        ol = o.lower()
        if v in ol or ol in v:
            return o
    return None


def validate_field(field: dict, value) -> Tuple[bool, Optional[str], str]:
    """Return (is_valid, normalised_value, message). Empty values are handled by the caller."""
    if value is None or str(value).strip() == "":
        return True, None, ""
    v, t, rules = str(value).strip(), field.get("type", "text"), field.get("validation") or {}
    if t == "cnic":
        n = norm_cnic(v)
        return (True, n, "") if n else (False, v, "CNIC must be 13 digits: #####-#######-#")
    if t == "phone":
        n = norm_phone(v)
        return (True, n, "") if n else (False, v, "Phone must look like 03XX-XXXXXXX")
    if t == "email":
        n = norm_email(v)
        return (True, n, "") if n else (False, v, "Enter a valid email address")
    if t == "date":
        n = norm_date(v)
        if not n:
            return False, v, "Date not understood (use DD-MM-YYYY)"
        d = datetime.strptime(n, "%Y-%m-%d").date()
        if rules.get("past") and d >= date.today():
            return False, n, "Date must be in the past"
        if rules.get("min_age") and (date.today() - d).days < rules["min_age"] * 365.25:
            return False, n, f"Must be at least {rules['min_age']} years old"
        return True, n, ""
    if t == "number":
        n = norm_number(v)
        if n is None:
            return False, v, "Enter a number"
        f = float(n)
        if "min" in rules and f < rules["min"]:
            return False, n, f"Must be at least {rules['min']}"
        if "max" in rules and f > rules["max"]:
            return False, n, f"Must be at most {rules['max']}"
        return True, n, ""
    if t == "select":
        m = match_option(v, field.get("options", []))
        return (True, m, "") if m else (False, v, "Choose one of: " + ", ".join(field.get("options", [])))
    if "min_length" in rules and len(v) < rules["min_length"]:
        return False, v, f"Too short (min {rules['min_length']} characters)"
    if "max_length" in rules and len(v) > rules["max_length"]:
        return False, v, f"Too long (max {rules['max_length']} characters)"
    return True, v, ""


def display_value(field: dict, value: str) -> str:
    """Human-friendly text for PDFs (dates become DD-MM-YYYY)."""
    if value and field.get("type") == "date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        y, m, d = value.split("-")
        return f"{d}-{m}-{y}"
    return value or ""
