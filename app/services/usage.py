"""Per-session API call counter. Powers the 'API calls used' indicator and the budget guard."""
from collections import OrderedDict

_MAX_SESSIONS = 500
_sessions: "OrderedDict[str, dict]" = OrderedDict()


def _get(sid: str) -> dict:
    sid = (sid or "anon")[:64]
    if sid not in _sessions:
        _sessions[sid] = {"llm": 0, "stt": 0, "cache_hits": 0}
        while len(_sessions) > _MAX_SESSIONS:
            _sessions.popitem(last=False)
    return _sessions[sid]


def add(sid: str, kind: str, n: int = 1) -> None:
    _get(sid)[kind] += n


def get(sid: str) -> dict:
    return dict(_get(sid))


def reset(sid: str) -> None:
    _sessions.pop((sid or "anon")[:64], None)
