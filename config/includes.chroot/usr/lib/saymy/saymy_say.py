"""Say Bar engine.

Type (or later: speak) what you want in any installed language. Intents are plain
JSON in <share>/say/intents/<lang>.json, so a translator can add a language without
touching code. Matching tries the user's language first and then every other
installed language, so mixing English and Kiswahili in one session just works.

Actions are language-neutral and built here. `handle()` never executes anything;
it returns a Result, and `run()` executes it. That split keeps the logic testable.
"""
import ast
import datetime
import json
import locale
import operator
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import saymy_i18n as i18n

SHARE = i18n.SHARE
DEFAULT_SEARCH = "https://duckduckgo.com/?q={q}"

APP_ALIASES = {
    "browser": "firefox", "internet": "firefox", "web": "firefox", "firefox": "firefox",
    "files": "pcmanfm", "file manager": "pcmanfm", "folders": "pcmanfm",
    "terminal": "foot", "console": "foot", "command line": "foot",
    "notes": "mousepad", "editor": "mousepad", "text editor": "mousepad", "notepad": "mousepad",
    "sound": "pavucontrol", "audio": "pavucontrol",
    "wifi": "settings", "network": "settings", "mipangilio": "settings",
}


@dataclass
class Result:
    intent: str = ""
    lang: str = ""
    slots: dict = field(default_factory=dict)
    exec: list = None        # argv to run, or None
    message: str = None      # text to show, or None


# --------------------------------------------------------------- matching
def normalize(text: str) -> str:
    text = text.replace("’", "'").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip("?!.,;: ")


def load_intents() -> dict:
    out = {}
    for f in sorted((SHARE / "say/intents").glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[data.get("language", f.stem)] = data.get("intents", [])
    return out


def _compile(pattern: str):
    parts = re.split(r"(\{\w+\})", pattern.lower())
    rx = ""
    literal = 0
    for p in parts:
        m = re.fullmatch(r"\{(\w+)\}", p)
        if m:
            rx += f"(?P<{m.group(1)}>.+)"
        else:
            rx += re.escape(p)
            literal += len(p)
    return re.compile(rx + r"$"), literal, "{" in pattern


def match(text: str, user_lang: str, intents: dict = None):
    """Return (intent_id, slots, lang) or None. Exact phrases beat slot phrases;
    longer literal text beats shorter; the user's language beats the others."""
    intents = intents if intents is not None else load_intents()
    text = normalize(text)
    order = [user_lang] + [l for l in sorted(intents) if l != user_lang]
    candidates = []
    for rank, lang in enumerate(order):
        for intent in intents.get(lang, []):
            for pat in intent["patterns"]:
                rx, literal, has_slot = _compile(pat)
                m = rx.match(text)
                if m:
                    candidates.append((has_slot, -literal, rank, intent["id"], m.groupdict(), lang))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[:3])
    _, _, _, iid, slots, lang = candidates[0]
    return iid, {k: v.strip() for k, v in slots.items()}, lang


# --------------------------------------------------------------- calculator
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}


def _prep_expr(expr: str) -> str:
    e = expr.lower()
    for a, b in ((" divided by ", "/"), (" times ", "*"), (" plus ", "+"), (" minus ", "-"),
                 ("×", "*"), ("÷", "/"), ("^", "**"), (",", "")):
        e = e.replace(a, b)
    e = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", e)
    return e.strip()


def safe_calc(expr: str):
    """Evaluate +, -, *, /, //, %, ** on plain numbers. Raises ValueError otherwise."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = ev(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(b) > 1000:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](a, b)
        raise ValueError("unsupported")
    try:
        val = ev(ast.parse(_prep_expr(expr), mode="eval"))
    except (SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
        raise ValueError(str(exc))
    if isinstance(val, float):
        val = int(val) if val.is_integer() else round(val, 10)
    return val


# --------------------------------------------------------------- app lookup
def _app_dirs():
    env = os.environ.get("SAYMY_APP_DIRS")
    if env:
        return [Path(p) for p in env.split(":") if p]
    dirs = [Path.home() / ".local/share/applications"]
    for base in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        dirs.append(Path(base) / "applications")
    return dirs


def _read_desktop(path: Path):
    name = generic = ""
    execline = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("[") and line.strip() != "[Desktop Entry]":
            break
        if line.startswith(("NoDisplay=true", "Hidden=true")):
            return None
        if line.startswith("Name=") and not name:
            name = line[5:].strip()
        elif line.startswith("GenericName=") and not generic:
            generic = line[12:].strip()
        elif line.startswith("Exec=") and not execline:
            execline = line[5:].strip()
    exe = os.path.basename(execline.split()[0]) if execline.split() else ""
    return name, generic, exe


def find_app(query: str):
    """Return a desktop-file id (e.g. 'firefox-esr.desktop') for a spoken app name, or None."""
    q = normalize(query)
    q = APP_ALIASES.get(q, q)
    best = None
    for d in _app_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            info = _read_desktop(f)
            if not info:
                continue
            name, generic, exe = (s.lower() for s in info)
            stem = f.stem.lower()
            if q in (name, stem, exe):
                score = 3
            elif name.startswith(q) or stem.startswith(q) or exe.startswith(q):
                score = 2
            elif q in name or q in generic:
                score = 1
            else:
                continue
            if best is None or score > best[0]:
                best = (score, f.name)
    return best[1] if best else None


# --------------------------------------------------------------- actions
def _config() -> dict:
    try:
        return json.loads((i18n.config_dir() / "say.json").read_text())
    except (OSError, ValueError):
        return {}


def _battery_message(lang):
    try:
        import saymy_power
        st = saymy_power.read_state()
    except Exception:
        st = None
    if not st or st.get("battery_pct") is None:
        return i18n.t("say.battery.none", lang)
    symbol = {"Charging": "⚡", "Full": "✓", "Discharging": "▼"}.get(st.get("battery_status"), "")
    return i18n.t("say.battery", lang, pct=st["battery_pct"], state=symbol)


def _data_message(lang):
    try:
        import saymy_data
        return i18n.t("say.data", lang, today=saymy_data.today_text())
    except Exception:
        return i18n.t("say.data", lang, today="–")


SIMPLE = {
    "lock": ["saymy-lock"],
    "shutdown": ["systemctl", "poweroff"],
    "restart": ["systemctl", "reboot"],
    "sleep": ["systemctl", "suspend"],
    "volume_up": ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+"],
    "volume_down": ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"],
    "mute": ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
    "brightness_up": ["brightnessctl", "set", "5%+"],
    "brightness_down": ["brightnessctl", "set", "5%-"],
    "space_study": ["saymy-space", "Study"], "space_business": ["saymy-space", "Business"],
    "space_home": ["saymy-space", "Home"], "space_developer": ["saymy-space", "Developer"],
    "doctor_network": ["saymy-doctor", "--topic", "network"], "doctor_power": ["saymy-doctor", "--topic", "power"],
    "doctor_slow": ["saymy-doctor", "--topic", "slow"], "doctor_all": ["saymy-doctor"],
    "night_on": ["saymy-night", "on"], "night_off": ["saymy-night", "off"],
    "drop": ["saymy-drop"],
    "look_dark": ["saymy-look", "mode", "dark"], "look_light": ["saymy-look", "mode", "light"],
    "language": ["saymy-language"],
    "install": ["saymy-install"],
}


def handle(text: str, lang: str = None, intents: dict = None) -> Result:
    lang = lang or i18n.current_language()
    m = match(text, lang, intents)
    if not m:
        return Result(message=i18n.t("say.unknown", lang, text=text.strip()), lang=lang)
    iid, slots, mlang = m
    r = Result(intent=iid, lang=mlang, slots=slots)
    # Reply in the language the user spoke the command in.
    reply = mlang if mlang in i18n.available_languages() else lang

    if iid in SIMPLE:
        r.exec = SIMPLE[iid]
    elif iid == "open_app":
        app = find_app(slots["app"])
        if app:
            r.exec = ["gtk-launch", app]
        else:
            r.message = i18n.t("say.app.notfound", reply, app=slots["app"])
    elif iid == "web_search":
        url = _config().get("search_url", DEFAULT_SEARCH).format(q=urllib.parse.quote_plus(slots["query"]))
        r.exec = ["xdg-open", url]
    elif iid == "battery":
        r.message = _battery_message(reply)
    elif iid == "time":
        r.message = i18n.t("say.time", reply, time=datetime.datetime.now().strftime("%H:%M"))
    elif iid == "date":
        try:
            locale.setlocale(locale.LC_TIME, "")
        except locale.Error:
            pass
        r.message = i18n.t("say.date", reply, date=datetime.datetime.now().strftime("%A, %d %B %Y"))
    elif iid == "data_used":
        r.message = _data_message(reply)
    elif iid == "calculate":
        try:
            r.message = i18n.t("say.calc", reply, expr=slots["expr"], result=safe_calc(slots["expr"]))
        except ValueError:
            r.message = i18n.t("say.calc.error", reply)
    elif iid == "help":
        r.message = i18n.t("say.help", reply)
    return r


def notify(text: str):
    try:
        subprocess.run(["notify-send", "-a", "Say Bar", "-i", "saymy", "Say Bar", text], check=False)
    except OSError:
        pass


def run(r: Result):
    if r.exec:
        subprocess.Popen(r.exec, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.message:
        notify(r.message)


def ask_interactively() -> str:
    """Open the Say Bar prompt (fuzzel in prompt-only mode)."""
    prompt = i18n.t("say.prompt") + " "
    p = subprocess.run(["fuzzel", "--dmenu", "--prompt-only", prompt, "--lines", "0"],
                       input="", capture_output=True, text=True)
    return p.stdout.strip()


def main(argv):
    dry = "--dry-run" in argv
    lang = None
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    words = [a for a in argv if a != "--dry-run"]
    text = " ".join(words) if words else ask_interactively()
    if not text:
        return 0
    r = handle(text, lang)
    if dry:
        print(json.dumps({"intent": r.intent, "lang": r.lang, "slots": r.slots,
                          "exec": r.exec, "message": r.message}, ensure_ascii=False))
    else:
        run(r)
    return 0 if r.intent else 1
