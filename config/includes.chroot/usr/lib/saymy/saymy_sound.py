"""SayMy sounds: event sounds from a pack (Savanna, Quiet, Classic, or Off).

Plays finished WAV files through PipeWire (pw-play), falling back to paplay or aplay. Silent when sounds are off,
when notifications are muted (Study space), unless the event is a safety alert. Never raises: a missing player or
file simply means no sound.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import saymy_i18n as i18n

SHARE = i18n.SHARE
PACKS_OFF = "Off"
EVENTS = ["login", "logout", "notify", "tick", "critical", "power-cut", "power-back", "battery-low", "received", "update-done", "error"]
ALWAYS = {"critical", "power-cut", "battery-low"}          # safety alerts ignore Do Not Disturb
DEFAULT = {"pack": "Savanna", "volume": 70}


def config_path() -> Path:
    return i18n.config_dir() / "sound.json"


def load() -> dict:
    cfg = dict(DEFAULT)
    try:
        cfg.update(json.loads(config_path().read_text()))
    except (OSError, ValueError):
        pass
    cfg["volume"] = max(0, min(100, int(cfg.get("volume", 70))))
    return cfg


def save(cfg: dict):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg))


def packs() -> list:
    d = SHARE / "sounds"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def set_pack(name: str) -> dict:
    if name != PACKS_OFF and name not in packs():
        raise ValueError("unknown sound pack; choose from " + ", ".join(packs() + [PACKS_OFF]))
    cfg = load()
    cfg["pack"] = name
    save(cfg)
    return cfg


def set_volume(value: int) -> dict:
    cfg = load()
    cfg["volume"] = max(0, min(100, int(value)))
    save(cfg)
    return cfg


def muted_now() -> bool:
    """True while notifications are on Do Not Disturb (the Study space)."""
    try:
        p = subprocess.run(["makoctl", "mode"], capture_output=True, text=True, timeout=2)
        return "dnd" in p.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False


def player_command(path: Path, volume: int):
    v = f"{volume / 100:.2f}"
    if shutil.which("pw-play"):
        return ["pw-play", "--volume", v, str(path)]
    if shutil.which("paplay"):
        return ["paplay", "--volume", str(int(65536 * volume / 100)), str(path)]
    if shutil.which("aplay"):
        return ["aplay", "-q", str(path)]
    return None


def sound_file(event: str, pack: str = None):
    cfg = load()
    pack = pack or cfg["pack"]
    if event not in EVENTS or pack == PACKS_OFF:
        return None
    f = SHARE / "sounds" / pack / f"{event}.wav"
    return f if f.is_file() else None


def play(event: str, pack: str = None, force: bool = False) -> bool:
    cfg = load()
    f = sound_file(event, pack)
    if not f or cfg["volume"] == 0:
        return False
    if not force and event not in ALWAYS and muted_now():
        return False
    cmd = player_command(f, cfg["volume"])
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
