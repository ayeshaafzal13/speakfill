"""Provider fallback chain: Gemini -> Groq -> (caller falls back to rules-only).

Safety features: per-provider sliding-window rate limiter, one retry with backoff on
429/5xx, per-session call budget, and never a raw provider error shown to the user.
"""
import asyncio
import json
import logging
import re
import time
from collections import deque
from typing import Optional, Tuple

from .. import config
from . import usage

log = logging.getLogger("llm")
TIMEOUT = 25.0


class ProviderError(Exception):
    def __init__(self, msg: str, retryable: bool = False):
        super().__init__(msg)
        self.retryable = retryable


class RateLimiter:
    """Sliding window: at most `per_minute` calls in any 60 s. Waits briefly, else refuses."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self.calls: deque = deque()
        self.lock = asyncio.Lock()

    async def acquire(self, max_wait: float = 12.0) -> bool:
        async with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                wait = 60 - (now - self.calls[0])
                if wait > max_wait:
                    return False
                await asyncio.sleep(wait)
            self.calls.append(time.monotonic())
            return True


def parse_json_loose(text: str) -> Optional[dict]:
    """Models sometimes wrap JSON in ``` fences or add chatter. Extract the first {...} block."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def _gemini(system: str, user: str) -> str:
    import httpx

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    gen_cfg = {"temperature": 0, "maxOutputTokens": 2048, "responseMimeType": "application/json"}
    if "2.5" in config.GEMINI_MODEL:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}  # no hidden thinking tokens = cheaper + faster
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    headers = {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=body, headers=headers)
    if r.status_code == 429 or r.status_code >= 500:
        raise ProviderError(f"gemini {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise ProviderError(f"gemini {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        raise ProviderError("gemini empty response")


async def _groq(system: str, user: str) -> str:
    import httpx

    body = {
        "model": config.GROQ_LLM_MODEL,
        "temperature": 0,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post("https://api.groq.com/openai/v1/chat/completions", json=body, headers=headers)
    if r.status_code == 429 or r.status_code >= 500:
        raise ProviderError(f"groq {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise ProviderError(f"groq {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise ProviderError("groq empty response")


_limiters = {"gemini": None, "groq": None}


def _limiter(name: str) -> RateLimiter:
    if _limiters[name] is None:
        _limiters[name] = RateLimiter(config.GEMINI_RPM if name == "gemini" else config.GROQ_RPM)
    return _limiters[name]


def available_providers() -> list:
    chain = []
    if config.GEMINI_API_KEY:
        chain.append(("gemini", _gemini))
    if config.GROQ_API_KEY:
        chain.append(("groq", _groq))
    return chain


async def call_json(system: str, user: str, session_id: str) -> Tuple[Optional[dict], str]:
    """Return (parsed_json, provider_name). (None, 'rules') means: use rules-only extraction."""
    if usage.get(session_id)["llm"] >= config.MAX_LLM_CALLS_PER_SESSION:
        log.warning("Session LLM budget reached")
        return None, "rules"
    for name, fn in available_providers():
        for attempt in (0, 1):
            if not await _limiter(name).acquire():
                break  # our own limiter says wait too long -> next provider
            usage.add(session_id, "llm")
            try:
                data = parse_json_loose(await fn(system, user))
                if data is not None:
                    return data, name
                break  # unparseable -> next provider, retrying rarely helps
            except ProviderError as e:
                log.warning("%s failed (attempt %d): %s", name, attempt + 1, e)
                if e.retryable and attempt == 0:
                    await asyncio.sleep(2.0)
                    continue
                break
            except Exception as e:  # network errors, timeouts
                log.warning("%s network error: %s", name, type(e).__name__)
                if attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                break
    return None, "rules"
