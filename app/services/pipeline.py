"""The heart of the app: rules -> cache -> ONE LLM call -> local validation -> local questions."""
import asyncio
import json
import logging
from typing import Dict, List, Optional

from .. import config
from . import cache, llm_router, rules, usage
from . import validators as V
from .textnorm import normalize_text

log = logging.getLogger("pipeline")

SYSTEM_PROMPT = (
    "You fill a form from a spoken transcript (Urdu script, Roman Urdu, English or a mix). "
    "Reply with ONLY a JSON object: keys are the given field ids, each value is "
    '{"value": string or null, "confidence": number 0 to 1}. '
    "Rules: never invent data; if a field is not clearly stated use null and confidence 0. "
    "Convert spoken numbers to digits. Dates as YYYY-MM-DD (day comes first in Pakistani speech). "
    "CNIC as 13 digits, phone as 11 digits starting 03. Write names, cities and institutions in English letters. "
    "For type select, value must be exactly one of the options. For type textarea keep the speaker's own "
    "language, lightly cleaned. The transcript may contain recognition errors: fix obvious ones but lower confidence."
)

_locks: Dict[str, asyncio.Lock] = {}


def session_lock(sid: str) -> asyncio.Lock:
    """One in-flight request per session, so double clicks never double-spend quota."""
    if len(_locks) > 1000:
        _locks.clear()
    return _locks.setdefault(sid or "anon", asyncio.Lock())


def compact_schema(fields: List[dict]) -> List[dict]:
    out = []
    for f in fields:
        item = {"id": f["id"], "type": f["type"], "label": f["label_en"]}
        if f.get("options"):
            item["options"] = f["options"]
        out.append(item)
    return out


def finalize(fields: List[dict], raw: Dict[str, dict]) -> Dict[str, dict]:
    """Validate/normalise every field locally and assign a colour status."""
    result = {}
    for f in fields:
        r = raw.get(f["id"]) or {}
        value = r.get("value")
        value = None if value is None or str(value).strip().lower() in ("", "null", "none") else str(value).strip()
        try:
            conf = float(r.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        message = ""
        if value is None:
            status = "missing" if f.get("required") else "empty"
            conf = 0.0
        else:
            ok, norm, message = V.validate_field(f, value)
            value = norm if norm is not None else value
            if not ok:
                status = "invalid"
            elif conf < 0.8:
                status = "check"
            else:
                status = "ok"
        result[f["id"]] = {"value": value, "confidence": round(conf, 2), "status": status, "message": message}
    return result


def unresolved_ids(fields: Dict[str, dict]) -> List[str]:
    """Which fields deserve a follow-up question: missing required, invalid, or low confidence."""
    out = []
    for fid, f in fields.items():
        if f["status"] in ("missing", "invalid") or (f["status"] == "check" and f["confidence"] < 0.6):
            out.append(fid)
    return out


def build_questions(form: dict, ids: List[str], fields: Dict[str, dict]) -> List[dict]:
    """Follow-up questions from templates. NO LLM call."""
    by_id = {f["id"]: f for f in form["fields"]}
    qs = []
    for fid in ids:
        f = by_id[fid]
        reason = fields.get(fid, {}).get("status", "missing")
        why_en = "Please say it again" if reason in ("invalid", "check") else "Please tell us"
        why_ur = "براہ کرم دوبارہ بتائیں" if reason in ("invalid", "check") else "براہ کرم بتائیں"
        qs.append(
            {
                "id": fid,
                "type": f["type"],
                "options": f.get("options"),
                "question_en": f"{why_en}: {f['label_en']}" + (f" (e.g. {f['example']})" if f.get("example") else ""),
                "question_ur": f"{why_ur}: {f['label_ur']}",
                "problem": fields.get(fid, {}).get("message", ""),
            }
        )
    return qs


def _package(form: dict, fields: Dict[str, dict], provider: str, cached: bool, sid: str, round_no: int = 0) -> dict:
    ids = unresolved_ids(fields)
    manual = []
    if round_no >= config.MAX_CLARIFY_ROUNDS:  # stop asking, hand the rest to the user
        manual, ids = ids, []
    return {
        "fields": fields,
        "unresolved": ids,
        "manual": manual,
        "questions": build_questions(form, ids, fields),
        "provider": provider,
        "cached": cached,
        "usage": usage.get(sid),
    }


async def extract(
    form: dict,
    transcript: str,
    sid: str,
    only_ids: Optional[List[str]] = None,
    offline_llm: Optional[dict] = None,
    round_no: int = 0,
) -> dict:
    transcript = normalize_text(transcript)[: config.MAX_TRANSCRIPT_CHARS]
    scope = [f for f in form["fields"] if only_ids is None or f["id"] in only_ids]
    raw: Dict[str, dict] = {}

    # 1) rules first (free)
    for fid, val in rules.extract(scope, transcript).items():
        raw[fid] = {"value": val, "confidence": 0.99}

    # 2) LLM only for what rules could not fill
    remaining = [f for f in scope if f["id"] not in raw]
    provider, cached = "rules", False
    if remaining and transcript:
        schema = compact_schema(remaining)
        key = cache.make_key(form["id"], schema, transcript)
        data = None
        if offline_llm is not None:
            data, provider = offline_llm, "offline-demo"
        elif (hit := cache.get(key)) is not None:
            data, provider, cached = hit["data"], hit["provider"], True
            usage.add(sid, "cache_hits")
        else:
            async with session_lock(sid):
                user = json.dumps({"schema": schema, "transcript": transcript}, ensure_ascii=False)
                data, provider = await llm_router.call_json(SYSTEM_PROMPT, user, sid)
            if data is not None:
                cache.set(key, {"data": data, "provider": provider})
        if data is not None:
            for f in remaining:
                item = data.get(f["id"])
                if isinstance(item, dict):
                    raw[f["id"]] = item
                elif isinstance(item, str):  # lenient: model returned bare strings
                    raw[f["id"]] = {"value": item, "confidence": 0.7}
        else:  # 3) rules-only fallback
            provider = "rules"
            for fid, val in rules.extract_weak(remaining, transcript).items():
                raw[fid] = {"value": val, "confidence": 0.6}

    fields = finalize(scope, raw)
    pkg = _package(form, fields, provider, cached, sid, round_no)
    return pkg


def apply_answers(form: dict, answers: Dict[str, str]) -> Dict[str, dict]:
    """Per-field follow-up answers typed/spoken into their own box: local rules only, 0 LLM calls."""
    by_id = {f["id"]: f for f in form["fields"]}
    raw = {}
    scope = []
    for fid, text in answers.items():
        if fid in by_id and str(text).strip():
            scope.append(by_id[fid])
            raw[fid] = {"value": rules.extract_single(by_id[fid], str(text)), "confidence": 1.0}
    return finalize(scope, raw)


def validate_all(form: dict, values: Dict[str, str], sid: str, round_no: int = 0) -> dict:
    """Used by guided mode and the final Confirm step. Pure local validation."""
    raw = {}
    for f in form["fields"]:
        v = values.get(f["id"])
        if v is not None and str(v).strip():
            raw[f["id"]] = {"value": rules.extract_single(f, str(v)), "confidence": 1.0}
    fields = finalize(form["fields"], raw)
    return _package(form, fields, "local", False, sid, round_no)
