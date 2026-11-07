"""SayMy i18n: tiny, dependency-free translation helper.

Every user-facing string in SayMy tools goes through t(key).
Catalogs live in <share>/i18n/<lang>.json. Missing keys fall back to English,
then to the key itself, so an unfinished translation never breaks a tool.
"""
import json
import os
from pathlib import Path

SHARE = Path(os.environ.get("SAYMY_SHARE", "/usr/share/saymy"))
FALLBACK = "en"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "saymy"


def available_languages() -> dict:
    """Return {code: native_name} for every installed catalog."""
    out = {}
    for f in sorted((SHARE / "i18n").glob("*.json")):
        try:
            meta = json.loads(f.read_text(encoding="utf-8")).get("_meta", {})
        except (OSError, ValueError):
            continue
        out[f.stem] = meta.get("name", f.stem)
    return out


def current_language() -> str:
    """User choice (~/.config/saymy/lang) > $LANG prefix > English."""
    try:
        choice = (config_dir() / "lang").read_text().strip()
        if choice:
            return choice
    except OSError:
        pass
    env = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "en").split(".")[0]
    return env.split("_")[0].lower() or FALLBACK


def _load(lang: str) -> dict:
    try:
        return json.loads((SHARE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def t(key: str, lang: str = None, **fmt) -> str:
    lang = lang or current_language()
    for code in (lang, FALLBACK):
        text = _load(code).get(key)
        if text:
            try:
                return text.format(**fmt)
            except (KeyError, IndexError):
                return text
    return key
