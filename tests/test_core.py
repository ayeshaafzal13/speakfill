import asyncio
import json

from app import config
from app.services import forms, llm_router, pdf_builder, pipeline, rules
from app.services import textnorm as T
from app.services import validators as V


def run(coro):
    return asyncio.run(coro)


def test_spoken_digits():
    assert T.normalize_text("zero teen zero zero ek do teen char panch chay saat") == "03001234567"
    assert T.normalize_text("mujhe do cheezein chahiye") == "mujhe do cheezein chahiye"  # 'do' alone untouched


def test_urdu_digits():
    assert V.norm_cnic("٣٥٢٠٢١٢٣٤٥٦٧١") == "35202-1234567-1"


def test_validators():
    assert V.norm_phone("+92 300 1234567") == "0300-1234567"
    assert V.norm_phone("12345") is None
    assert V.norm_email("Ali @ Gmail.com") == "ali@gmail.com"
    assert V.find_dates("15 March 2001") == ["2001-03-15"]
    assert V.find_dates("15/03/2001") == ["2001-03-15"]
    assert V.find_dates("3 sitambar 1999") == ["1999-09-03"]
    ok, _, msg = V.validate_field({"type": "date", "validation": {"past": True}}, "2999-01-01")
    assert not ok and msg


def test_rules_unambiguous_only():
    f = [{"id": "p1", "type": "phone"}, {"id": "p2", "type": "phone"}]
    assert rules.extract(f, "0300 1234567") == {}  # two phone fields -> leave to LLM
    f = [{"id": "cnic", "type": "cnic"}]
    assert rules.extract(f, "cnic 35202-1234567-1")["cnic"] == "35202-1234567-1"


def test_templates_load():
    all_forms = forms.load_all()
    assert len(all_forms) >= 3
    for form in all_forms.values():
        for f in form["fields"]:
            assert {"id", "label_en", "label_ur", "type", "required"} <= set(f)


def test_demo_needs_zero_llm_calls_and_asks_for_cnic():
    demo = json.loads(config.DEMO_FILE.read_text(encoding="utf-8"))
    form = forms.get(demo["form_id"])
    res = run(pipeline.extract(form, demo["transcript"], "t-demo", offline_llm=demo["llm_response"]))
    assert res["unresolved"] == ["cnic"]
    assert res["fields"]["phone"]["value"] == "0300-1234567"
    ans = pipeline.apply_answers(form, demo["followup_answers"])
    assert ans["cnic"]["status"] == "ok"


def test_llm_fallback_to_rules_when_no_keys(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    form = forms.get("job_application")
    res = run(pipeline.extract(form, "my name is Sara Khan, Bachelor's", "t-rules"))
    assert res["provider"] == "rules" and res["fields"]["full_name"]["value"] == "Sara Khan"


def test_cache_prevents_second_call(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_FILE", tmp_path / "c.json")
    calls = []

    async def fake(system, user, sid):
        calls.append(1)
        return {"full_name": {"value": "Ali", "confidence": 0.9}}, "gemini"

    monkeypatch.setattr(llm_router, "call_json", fake)
    form = forms.get("job_application")
    run(pipeline.extract(form, "unique cache test sentence", "t-c"))
    second = run(pipeline.extract(form, "unique cache test sentence", "t-c"))
    assert len(calls) == 1 and second["cached"]


def test_parse_json_loose():
    assert llm_router.parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm_router.parse_json_loose("no json") is None


def test_pdf_builds():
    form = forms.get("job_application")
    pdf = pdf_builder.build_pdf(form, {"full_name": "Ali Raza", "address": "ماڈل ٹاؤن لاہور"})
    assert pdf[:4] == b"%PDF"
