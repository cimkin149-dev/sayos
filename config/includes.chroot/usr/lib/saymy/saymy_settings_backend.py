"""SayMy Settings backend: everything the Settings app does, without any GUI.

Each function calls a standard Linux tool (nmcli, wpctl, brightnessctl, powerprofilesctl) and
degrades gracefully if it is missing. SAYMY_DEMO=1 returns sample data, for screenshots and tests.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import saymy_i18n as i18n

DEFAULT_ACCENT = "#FF8A1F"
ACCENTS = {"Sunrise": "#FF8A1F", "Gold": "#F5B93A", "Leaf": "#3FA66B", "Lake": "#2F8FD1", "Hibiscus": "#E0445B"}


def demo() -> bool:
    return bool(os.environ.get("SAYMY_DEMO"))


def run(cmd, timeout=8):
    """Run a command. Returns (ok, stdout). Missing tools and timeouts return (False, '')."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, ""


# ------------------------------------------------------------------ network
def _split_terse(line: str):
    """nmcli -t separates fields with ':' and escapes literal colons as '\\:'."""
    parts, cur, i = [], "", 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
        elif line[i] == ":":
            parts.append(cur)
            cur = ""
            i += 1
        else:
            cur += line[i]
            i += 1
    parts.append(cur)
    return parts


def parse_wifi(text: str) -> list:
    """Parse `nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list` into a clean list."""
    seen, out = {}, []
    for line in text.splitlines():
        f = _split_terse(line)
        if len(f) < 4 or not f[1]:
            continue
        item = {"connected": f[0].strip() == "*", "ssid": f[1], "signal": int(f[2] or 0),
                "secure": f[3].strip() not in ("", "--")}
        old = seen.get(item["ssid"])
        if old is None:
            seen[item["ssid"]] = item
            out.append(item)
        elif item["connected"] or item["signal"] > old["signal"]:
            old.update(item)
    out.sort(key=lambda w: (not w["connected"], -w["signal"]))
    return out


def wifi_list() -> list:
    if demo():
        return [{"connected": True, "ssid": "Kampala-Home", "signal": 82, "secure": True},
                {"connected": False, "ssid": "MakCampus", "signal": 64, "secure": True},
                {"connected": False, "ssid": "Cafe Guest", "signal": 41, "secure": False}]
    ok, out = run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "auto"], 15)
    return parse_wifi(out) if ok else []


def wifi_enabled() -> bool:
    if demo():
        return True
    ok, out = run(["nmcli", "radio", "wifi"])
    return ok and out.strip() == "enabled"


def wifi_set(on: bool):
    return run(["nmcli", "radio", "wifi", "on" if on else "off"])[0]


def wifi_connect(ssid: str, password: str = ""):
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    return run(cmd, 30)


# ------------------------------------------------------------------ display and sound
def parse_brightness(text: str):
    """brightnessctl -m prints: device,class,current,percent%,max"""
    f = text.strip().split(",")
    if len(f) >= 4 and f[3].rstrip("%").isdigit():
        return int(f[3].rstrip("%"))
    return None


def brightness_get():
    if demo():
        return 70
    ok, out = run(["brightnessctl", "-m"])
    return parse_brightness(out) if ok else None


def brightness_set(pct: int):
    return run(["brightnessctl", "set", f"{max(1, min(100, int(pct)))}%"])[0]


def parse_volume(text: str):
    """wpctl get-volume prints: 'Volume: 0.60' or 'Volume: 0.60 [MUTED]'. Returns (percent, muted)."""
    m = re.search(r"Volume:\s*([0-9.]+)", text)
    if not m:
        return None, False
    return round(float(m.group(1)) * 100), "[MUTED]" in text


def volume_get():
    if demo():
        return 60, False
    ok, out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    return parse_volume(out) if ok else (None, False)


def volume_set(pct: int):
    return run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{max(0, min(100, int(pct)))}%"])[0]


def mute_set(on: bool):
    return run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if on else "0"])[0]


# ------------------------------------------------------------------ power
PROFILES = ["power-saver", "balanced", "performance"]


def profile_get():
    if demo():
        return "balanced"
    ok, out = run(["powerprofilesctl", "get"])
    return out if ok else None


def profile_set(name: str):
    return name in PROFILES and run(["powerprofilesctl", "set", name])[0]


def power_summary() -> dict:
    """Battery state plus the 30-day outage diary from the power-cut guard."""
    import saymy_power
    st = saymy_power.read_state()
    di = saymy_power.diary_summary()
    if demo():
        st = {"ac": True, "battery_pct": 82, "battery_status": "Charging"}
        di = {"cuts": 6, "seconds": 7 * 3600 + 1800}
    return {"state": st, "cuts": di["cuts"], "hours": round(di["seconds"] / 3600, 1)}


# ------------------------------------------------------------------ appearance
def appearance_path() -> Path:
    return i18n.config_dir() / "appearance.json"


def load_appearance() -> dict:
    try:
        return json.loads(appearance_path().read_text())
    except (OSError, ValueError):
        return {"accent": DEFAULT_ACCENT, "follow_sky": False}


def save_appearance(cfg: dict):
    appearance_path().parent.mkdir(parents=True, exist_ok=True)
    appearance_path().write_text(json.dumps(cfg))


def normalize_hex(value: str) -> str:
    v = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", v):
        raise ValueError("accent must be a 6 digit hex colour like #FF8A1F")
    return "#" + v.upper()


def _swap(path: Path, old: str, new: str) -> bool:
    try:
        text = path.read_text()
    except OSError:
        return False
    updated = re.sub(re.escape(old), new, text, flags=re.I)
    if updated != text:
        path.write_text(updated)
        return True
    return False


def apply_accent(new_hex: str, home: Path = None, reload: bool = True) -> list:
    """Re-colour the whole desktop: panel, launcher, notifications, window borders, GTK apps.
    Returns the list of files changed."""
    new = normalize_hex(new_hex)
    cfg = load_appearance()
    old = normalize_hex(cfg.get("accent", DEFAULT_ACCENT))
    home = home or Path.home()
    changed = []
    waybar = home / ".config/waybar/style.css"
    try:
        text = waybar.read_text()
        out = re.sub(r"(@define-color\s+sun\s+)#[0-9a-fA-F]{6}", r"\g<1>" + new, text)
        if out != text:
            waybar.write_text(out)
            changed.append(str(waybar))
    except OSError:
        pass
    for rel, a, b in ((".config/fuzzel/fuzzel.ini", old[1:], new[1:]),
                      (".config/mako/config", old, new),
                      (".config/gtk-3.0/gtk.css", old, new),
                      (".config/gtk-4.0/gtk.css", old, new)):
        if _swap(home / rel, a, b):
            changed.append(rel)
    # window borders: labwc reads a per-user copy of the theme first
    user_theme = home / ".local/share/themes/SayMy/labwc/themerc"
    if not user_theme.exists():
        system_theme = Path("/usr/share/themes/SayMy/labwc/themerc")
        if system_theme.exists():
            user_theme.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(system_theme, user_theme)
    if _swap(user_theme, old, new):
        changed.append(str(user_theme))
    cfg["accent"] = new
    save_appearance(cfg)
    if reload and not demo():
        run(["pkill", "-SIGUSR2", "waybar"])
        run(["makoctl", "reload"])
        run(["labwc", "--reconfigure"])
    return changed


# ------------------------------------------------------------------ about
def system_info() -> dict:
    info = {"os": "SayMy OS", "kernel": os.uname().release, "cpu": "", "ram": "", "disk": ""}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                info["os"] = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                info["ram"] = f"{int(line.split()[1]) / 1048576:.1f} GB"
                break
        du = shutil.disk_usage("/")
        info["disk"] = f"{du.free / 1e9:.0f} GB free of {du.total / 1e9:.0f} GB"
    except (OSError, ValueError):
        pass
    return info
