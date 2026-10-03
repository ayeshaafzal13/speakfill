"""Tiny JSON-backed cache. Same transcript + same schema => zero repeat API calls."""
import hashlib
import json
import logging
from typing import Any, Optional

from .. import config

log = logging.getLogger("cache")
_MAX_ITEMS = 500
_data: dict = {}
_loaded = False


def make_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load() -> None:
    global _loaded, _data
    if _loaded:
        return
    _loaded = True
    try:
        if config.CACHE_FILE.exists():
            _data = json.loads(config.CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # corrupted cache is not fatal
        log.warning("Cache file unreadable, starting empty")
        _data = {}


def get(key: str) -> Optional[Any]:
    _load()
    return _data.get(key)


def set(key: str, value: Any) -> None:  # noqa: A001
    _load()
    _data[key] = value
    while len(_data) > _MAX_ITEMS:
        _data.pop(next(iter(_data)))
    try:
        config.CACHE_FILE.write_text(json.dumps(_data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # read-only filesystems (serverless) are fine, memory cache still works
        pass
