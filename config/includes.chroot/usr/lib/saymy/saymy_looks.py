"""SayMy Looks: how the desktop looks, and how to share it.

A Look is a small JSON file: a name, an accent colour, light or dark, and where the panel sits and how tall it is.
Looks are pure data. Applying one never runs code, so a Look from a friend or a community site is safe to try:
every field is validated, unknown fields are ignored, and values are limited to sane ranges.
"""
import json
import re
from pathlib import Path

import saymy_settings_backend as be

MAX_LOOK_BYTES = 4096

PALETTES = {
    "dark": {"base": "#0C1A2A", "surface": "#14283C", "raised": "#1E3A55", "text": "#F3E9D8", "muted": "#9FB3C8"},
    "light": {"base": "#F7F1E6", "surface": "#FFFFFF", "raised": "#E4D9C6", "text": "#14283C", "muted": "#5C7189"},
}
RGBA_BASE = {"dark": "12, 26, 42", "light": "247, 241, 230"}
SIZES = {"Compact": 36, "Normal": 46, "Large": 58}

PRESETS = {
    "Sunrise": {"name": "Sunrise", "accent": "#FF8A1F", "mode": "dark", "panel_position": "bottom", "panel_height": 46},
    "Lake Night": {"name": "Lake Night", "accent": "#2F8FD1", "mode": "dark", "panel_position": "bottom", "panel_height": 46},
    "Paper": {"name": "Paper", "accent": "#D9650D", "mode": "light", "panel_position": "bottom", "panel_height": 46},
    "Compact Top Bar": {"name": "Compact Top Bar", "accent": "#3FA66B", "mode": "dark", "panel_position": "top", "panel_height": 36},
}


# ------------------------------------------------------------------ colour swapping
def swap_palette(text: str, src: str, dst: str) -> str:
    """Replace every palette colour of mode `src` with its `dst` twin in ONE pass (no chained replacements)."""
    if src == dst:
        return text
    mapping = {}
    for key, old in PALETTES[src].items():
        new = PALETTES[dst][key]
        mapping[old.lstrip("#").upper()] = new.lstrip("#").upper()
    pattern = re.compile("|".join(map(re.escape, mapping)), re.I)
    out = pattern.sub(lambda m: mapping[m.group(0).upper()], text)
    return re.sub(r"rgba\(\s*" + re.escape(RGBA_BASE[src]).replace(r"\ ", r"\s*") + r"\s*,", f"rgba({RGBA_BASE[dst]},", out)


def apply_mode(mode: str, home: Path = None, reload: bool = True) -> list:
    if mode not in PALETTES:
        raise ValueError("mode must be dark or light")
    cfg = be.load_appearance()
    current = cfg.get("mode", "dark")
    home = home or Path.home()
    changed = []
    files = [".config/waybar/style.css", ".config/fuzzel/fuzzel.ini", ".config/mako/config", ".config/foot/foot.ini",
             ".local/share/themes/SayMy/labwc/themerc"]
    for rel in files:
        p = home / rel
        try:
            text = p.read_text()
        except OSError:
            continue
        out = swap_palette(text, current, mode)
        if out != text:
            p.write_text(out)
            changed.append(rel)
    for rel, old, new in ((".config/labwc/environment", "GTK_THEME=Adwaita-dark" if mode == "light" else "GTK_THEME=Adwaita",
                           "GTK_THEME=Adwaita" if mode == "light" else "GTK_THEME=Adwaita-dark"),
                          (".config/gtk-3.0/settings.ini", f"gtk-application-prefer-dark-theme={0 if mode == 'dark' else 1}",
                           f"gtk-application-prefer-dark-theme={1 if mode == 'dark' else 0}")):
        p = home / rel
        try:
            text = p.read_text()
        except OSError:
            continue
        if old in text:
            p.write_text(text.replace(old, new))
            changed.append(rel)
    cfg["mode"] = mode
    be.save_appearance(cfg)
    if reload and not be.demo():
        be.run(["pkill", "-SIGUSR2", "waybar"])
        be.run(["makoctl", "reload"])
        be.run(["labwc", "--reconfigure"])
    return changed


# ------------------------------------------------------------------ panel
def apply_panel(position: str, height: int, home: Path = None, reload: bool = True) -> bool:
    if position not in ("top", "bottom"):
        raise ValueError("panel position must be top or bottom")
    height = int(height)
    if not 28 <= height <= 72:
        raise ValueError("panel height must be between 28 and 72")
    home = home or Path.home()
    path = home / ".config/waybar/config.jsonc"
    try:
        cfg = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    cfg["position"] = position
    cfg["height"] = height
    cfg["margin"] = "0 12 10 12" if position == "bottom" else "10 12 0 12"
    path.write_text(json.dumps(cfg, indent=2))
    a = be.load_appearance()
    a["panel_position"], a["panel_height"] = position, height
    be.save_appearance(a)
    if reload and not be.demo():
        be.run(["pkill", "-SIGUSR2", "waybar"])
    return True


# ------------------------------------------------------------------ looks
def validate_look(data) -> dict:
    """Return a clean Look or raise ValueError. Never trusts the input."""
    if not isinstance(data, dict):
        raise ValueError("a Look must be a JSON object")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a Look needs a name")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:40]
    look = {"name": name, "accent": be.normalize_hex(str(data.get("accent", be.DEFAULT_ACCENT)))}
    mode = data.get("mode", "dark")
    if mode not in PALETTES:
        raise ValueError("mode must be dark or light")
    look["mode"] = mode
    pos = data.get("panel_position", "bottom")
    if pos not in ("top", "bottom"):
        raise ValueError("panel_position must be top or bottom")
    look["panel_position"] = pos
    h = data.get("panel_height", 46)
    if isinstance(h, bool) or not isinstance(h, int) or not 28 <= h <= 72:
        raise ValueError("panel_height must be a whole number from 28 to 72")
    look["panel_height"] = h
    return look


def current_look(name: str = "My Look") -> dict:
    a = be.load_appearance()
    return validate_look({"name": name, "accent": a.get("accent", be.DEFAULT_ACCENT), "mode": a.get("mode", "dark"),
                          "panel_position": a.get("panel_position", "bottom"), "panel_height": a.get("panel_height", 46)})


def apply_look(look: dict, home: Path = None, reload: bool = True) -> dict:
    look = validate_look(look)
    apply_mode(look["mode"], home=home, reload=False)
    be.apply_accent(look["accent"], home=home, reload=False)
    apply_panel(look["panel_position"], look["panel_height"], home=home, reload=False)
    a = be.load_appearance()
    a["follow_sky"] = False
    a["look"] = look["name"]
    be.save_appearance(a)
    if reload and not be.demo():
        be.run(["pkill", "-SIGUSR2", "waybar"])
        be.run(["makoctl", "reload"])
        be.run(["labwc", "--reconfigure"])
    return look


def export_look(path, name: str = "My Look") -> dict:
    look = current_look(name)
    Path(path).write_text(json.dumps(look, indent=1, ensure_ascii=False))
    return look


def import_look(path, home: Path = None, reload: bool = True) -> dict:
    p = Path(path)
    if p.stat().st_size > MAX_LOOK_BYTES:
        raise ValueError("that file is too big to be a Look")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        raise ValueError("that file is not a valid Look")
    return apply_look(data, home=home, reload=reload)
