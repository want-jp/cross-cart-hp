import json
from pathlib import Path
from functools import lru_cache

from app.config import DEFAULT_LANG

I18N_DIR = Path(__file__).resolve().parent / "i18n"


@lru_cache(maxsize=8)
def get_translations(lang: str) -> dict:
    """Load translations for the given language. Falls back to default."""
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        path = I18N_DIR / f"{DEFAULT_LANG}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
