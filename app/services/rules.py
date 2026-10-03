"""Regex-first extraction. Cheap, free, deterministic. The LLM only sees what is left."""
import re
from typing import Dict, List, Optional

from . import validators as V
from .textnorm import normalize_text

CNIC_FIND = re.compile(r"(?<!\d)\d{5}[- ]?\d{7}[- ]?\d(?!\d)")
PHONE_FIND = re.compile(r"(?<!\d)(?:\+?92[- ]?|0)?3\d{2}[- ]?\d{7}(?!\d)")
EMAIL_FIND = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
SPOKEN_EMAIL = re.compile(
    r"([A-Za-z0-9._]+)\s+(?:at the rate|at)\s+(gmail|yahoo|hotmail|outlook)\s+dot\s+com", re.I
)


def _unique(items: List[str]) -> List[str]:
    seen = []
    for i in items:
        if i and i not in seen:
            seen.append(i)
    return seen


def find_cnics(text: str) -> List[str]:
    return _unique([V.norm_cnic(m) for m in CNIC_FIND.findall(text)])


def find_phones(text: str) -> List[str]:
    text = CNIC_FIND.sub(" ", text)
    return _unique([V.norm_phone(m) for m in PHONE_FIND.findall(text)])


def find_emails(text: str) -> List[str]:
    text = SPOKEN_EMAIL.sub(lambda m: f"{m.group(1)}@{m.group(2)}.com", text)
    return _unique([V.norm_email(m) for m in EMAIL_FIND.findall(text)])


FINDERS = {"cnic": find_cnics, "phone": find_phones, "email": find_emails, "date": V.find_dates}


def extract(fields: List[dict], text: str) -> Dict[str, str]:
    """Fill a field only when it is unambiguous: exactly one such field AND exactly one match."""
    text = normalize_text(text)
    out: Dict[str, str] = {}
    for t, finder in FINDERS.items():
        same = [f for f in fields if f.get("type") == t]
        if len(same) == 1:
            hits = finder(text)
            if len(hits) == 1:
                out[same[0]["id"]] = hits[0]
    return out


def extract_single(field: dict, text: str) -> Optional[str]:
    """Interpret a short typed/spoken answer for one field (used for follow-up answers)."""
    text = normalize_text(text)
    t = field.get("type", "text")
    if t in FINDERS:
        hits = FINDERS[t](text)
        return hits[0] if hits else text.strip() or None
    if t == "select":
        return V.match_option(text, field.get("options", [])) or text.strip() or None
    if t == "number":
        return V.norm_number(text) or text.strip() or None
    return text.strip() or None


_NAME_PATTERNS = [
    re.compile(r"mera\s+(?:poora\s+|pura\s+)?naam\s+(.+?)\s+(?:hai|he|h)\b", re.I),
    re.compile(r"my\s+(?:full\s+)?name\s+is\s+([A-Za-z][A-Za-z .'-]{1,40}?)(?:[,.]|\s+and\b|\s+i\b|$)", re.I),
    re.compile(r"میرا\s+(?:پورا\s+)?نام\s+(.+?)\s+ہے"),
]


def extract_weak(fields: List[dict], text: str) -> Dict[str, str]:
    """Last-resort extraction when every LLM is unavailable: names + select options."""
    text = normalize_text(text)
    out: Dict[str, str] = {}
    name_field = next((f for f in fields if f["id"] in ("full_name", "name", "applicant_name")), None)
    if name_field:
        for rx in _NAME_PATTERNS:
            m = rx.search(text)
            if m:
                out[name_field["id"]] = m.group(1).strip().title()
                break
    low = text.lower()
    for f in fields:
        if f.get("type") == "select":
            hits = [o for o in f.get("options", []) if o.lower() in low]
            if len(hits) == 1:
                out[f["id"]] = hits[0]
    return out
