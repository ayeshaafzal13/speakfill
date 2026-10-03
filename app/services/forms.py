"""Built-in form templates (JSON files in app/schemas). Loading costs zero API calls."""
import json
from functools import lru_cache
from typing import Dict, Optional

from .. import config


@lru_cache(maxsize=1)
def load_all() -> Dict[str, dict]:
    forms = {}
    for p in sorted(config.SCHEMA_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        forms[data["id"]] = data
    return forms


def get(form_id: str) -> Optional[dict]:
    return load_all().get(form_id)


def summaries() -> list:
    return [
        {"id": f["id"], "title_en": f["title_en"], "title_ur": f["title_ur"], "field_count": len(f["fields"])}
        for f in load_all().values()
    ]
