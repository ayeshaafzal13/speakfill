"""SpeakFill - FastAPI backend. Run: uvicorn app.main:app --reload"""
import json
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .services import forms as forms_svc
from .services import llm_router, pdf_builder, pipeline, stt, usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

app = FastAPI(title="SpeakFill", version="1.0")
if config.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"]
    )


@app.exception_handler(Exception)
async def friendly_errors(request: Request, exc: Exception):
    """Never leak a raw stack trace to the browser."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Your data is safe, please try again."})


# ---------- request models ----------
class ExtractReq(BaseModel):
    form_id: str
    transcript: str = Field(default="", max_length=config.MAX_TRANSCRIPT_CHARS * 2)
    session_id: str = "anon"
    demo: bool = False


class ClarifyReq(BaseModel):
    form_id: str
    unresolved: List[str]
    answers: Dict[str, str] = {}
    answer_text: str = ""
    round: int = 0
    session_id: str = "anon"


class ValidateReq(BaseModel):
    form_id: str
    values: Dict[str, str]
    session_id: str = "anon"


class PdfReq(BaseModel):
    form_id: str
    values: Dict[str, str]


def _form(form_id: str) -> dict:
    form = forms_svc.get(form_id)
    if not form:
        raise HTTPException(404, "Unknown form")
    return form


# ---------- endpoints ----------
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "providers": [n for n, _ in llm_router.available_providers()],
        "stt_fallback": bool(config.GROQ_API_KEY),
        "urdu_font": bool(pdf_builder.urdu_font_name()),
        "forms": len(forms_svc.load_all()),
    }


@app.get("/api/forms")
def list_forms():
    return forms_svc.summaries()


@app.get("/api/forms/{form_id}")
def get_form(form_id: str):
    return _form(form_id)


@app.get("/api/usage")
def get_usage(session_id: str = "anon"):
    return usage.get(session_id)


@app.get("/api/demo")
def demo_info():
    """Pre-recorded transcript for the offline demo mode (works with every API down)."""
    d = json.loads(config.DEMO_FILE.read_text(encoding="utf-8"))
    return {"form_id": d["form_id"], "transcript": d["transcript"], "followup_answers": d["followup_answers"]}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), lang: str = Form("ur"), session_id: str = Form("anon")):
    data = await audio.read()
    if not data or len(data) > config.MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio is empty or too large (max 10 MB)")
    if audio.content_type and not audio.content_type.startswith(("audio/", "video/webm", "application/octet-stream")):
        raise HTTPException(415, "Unsupported audio type")
    try:
        text = await stt.transcribe(data, audio.filename, audio.content_type, lang, session_id)
    except stt.STTUnavailable as e:
        raise HTTPException(503, str(e))
    return {"text": text, "usage": usage.get(session_id)}


@app.post("/api/extract")
async def extract(req: ExtractReq):
    form = _form(req.form_id)
    offline = None
    transcript = req.transcript
    if req.demo:
        d = json.loads(config.DEMO_FILE.read_text(encoding="utf-8"))
        offline, transcript = d["llm_response"], d["transcript"]
    if not transcript.strip():
        raise HTTPException(400, "Please speak or type something first")
    return await pipeline.extract(form, transcript, req.session_id, offline_llm=offline)


@app.post("/api/clarify")
async def clarify(req: ClarifyReq):
    form = _form(req.form_id)
    round_no = req.round + 1
    updated = pipeline.apply_answers(form, req.answers)  # typed per-field answers: 0 LLM calls

    todo = [i for i in req.unresolved if updated.get(i, {}).get("status") not in ("ok", "check")]
    if req.answer_text.strip() and todo:  # one batched call for the whole spoken answer
        res = await pipeline.extract(form, req.answer_text, req.session_id, only_ids=todo)
        for fid, f in res["fields"].items():
            if f["value"] is not None:
                updated[fid] = f

    still = pipeline.unresolved_ids(updated)
    remaining = [i for i in req.unresolved if i not in updated or i in still]
    manual: List[str] = []
    if round_no >= config.MAX_CLARIFY_ROUNDS:
        manual, remaining = remaining, []
    return {
        "fields": updated,
        "unresolved": remaining,
        "manual": manual,
        "questions": pipeline.build_questions(form, remaining, updated),
        "usage": usage.get(req.session_id),
    }


@app.post("/api/validate")
def validate(req: ValidateReq):
    """Local validation only (guided mode + final Confirm). Never calls an LLM."""
    return pipeline.validate_all(_form(req.form_id), req.values, req.session_id)


@app.post("/api/pdf")
def make_pdf(req: PdfReq):
    form = _form(req.form_id)
    checked = pipeline.validate_all(form, req.values, "pdf")["fields"]
    clean = {fid: (f["value"] or req.values.get(fid, "")) for fid, f in checked.items()}
    pdf = pdf_builder.build_pdf(form, clean)
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{form["id"]}.pdf"'}
    )


# Frontend (must be mounted LAST so it doesn't shadow /api)
app.mount("/", StaticFiles(directory=str(config.ROOT_DIR / "web"), html=True), name="web")
