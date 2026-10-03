"""Fallback speech-to-text via Groq Whisper (only used when browser STT is unavailable)."""
import logging

from .. import config
from . import usage

log = logging.getLogger("stt")


class STTUnavailable(Exception):
    pass


async def transcribe(audio: bytes, filename: str, content_type: str, lang: str, session_id: str) -> str:
    import httpx

    if not config.GROQ_API_KEY:
        raise STTUnavailable("Server has no speech-to-text key. Please type your answer instead.")
    if usage.get(session_id)["stt"] >= config.MAX_STT_CALLS_PER_SESSION:
        raise STTUnavailable("Voice limit reached for this session. Please type instead.")
    data = {"model": config.GROQ_STT_MODEL, "response_format": "json", "temperature": "0"}
    if lang in ("ur", "en", "pa", "ps", "sd"):
        data["language"] = lang
    files = {"file": (filename or "audio.webm", audio, content_type or "audio/webm")}
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    usage.add(session_id, "stt")
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions", data=data, files=files, headers=headers
            )
    except Exception as e:
        log.warning("whisper network error %s", type(e).__name__)
        raise STTUnavailable("Could not reach the speech service. Please type instead.")
    if r.status_code != 200:
        log.warning("whisper status %s", r.status_code)
        raise STTUnavailable("Speech service is busy. Please try again or type instead.")
    return (r.json().get("text") or "").strip()
