"""Wallpaper settings and service control for SayMy.

Modes: live  (Living Sky, drawn by code, animated)  |  sky  (four sky photos that change with the hour)
       image (a picture you choose)
Config lives in appearance.json under "wallpaper". Looks may only name a scene, never a file path.
"""
import os
import signal
import subprocess
from pathlib import Path

import saymy_i18n as i18n
import saymy_settings_backend as be

MODES = ("live", "sky", "image")
ANIMATE = ("auto", "always", "never")
SCENES = ["Savanna", "Highlands", "Lakeshore"]
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT = {"mode": "live", "scene": "Savanna", "animate": "auto", "image": ""}


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "saymy"


def load() -> dict:
    cfg = dict(DEFAULT)
    cfg.update(be.load_appearance().get("wallpaper", {}) or {})
    if cfg["mode"] not in MODES:
        cfg["mode"] = DEFAULT["mode"]
    if cfg["scene"] not in SCENES:
        cfg["scene"] = DEFAULT["scene"]
    if cfg["animate"] not in ANIMATE:
        cfg["animate"] = DEFAULT["animate"]
    return cfg


def valid_image(path: str) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in IMAGE_EXT and p.stat().st_size < 60 * 1024 * 1024


def set_wallpaper(mode=None, scene=None, animate=None, image=None, reload=True) -> dict:
    cfg = load()
    if mode is not None:
        if mode not in MODES:
            raise ValueError("mode must be live, sky or image")
        cfg["mode"] = mode
    if scene is not None:
        if scene not in SCENES:
            raise ValueError("unknown scene; choose from " + ", ".join(SCENES))
        cfg["scene"] = scene
    if animate is not None:
        if animate not in ANIMATE:
            raise ValueError("animate must be auto, always or never")
        cfg["animate"] = animate
    if image is not None:
        if not valid_image(image):
            raise ValueError("that is not a usable picture (png, jpg or webp, under 60 MB)")
        cfg["image"] = str(Path(image).resolve())
    if cfg["mode"] == "image" and not (cfg["image"] and valid_image(cfg["image"])):
        raise ValueError("choose a picture first")
    a = be.load_appearance()
    a["wallpaper"] = cfg
    be.save_appearance(a)
    if reload and not be.demo():
        restart()
    return cfg


def stop():
    """Stop whatever draws the wallpaper (never matches by command line, only by saved process ids)."""
    for name in ("wallpaper.pid", "live.pid", "sky.pid"):
        f = cache_dir() / name
        try:
            pid = int(f.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass
        try:
            f.unlink()
        except OSError:
            pass
    be.run(["pkill", "-x", "swaybg"])


def start():
    subprocess.Popen(["saymy-wallpaper"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def restart():
    stop()
    start()


def thumbnails(hour=None, size=(320, 180)):
    """PNG bytes for each scene at the current time, for the Settings picker."""
    import saymy_live
    hour = saymy_live.hour_now() if hour is None else hour
    return {s: saymy_live.png_bytes(size[0], size[1], s, hour, t=2.0) for s in SCENES}


def command_for(cfg: dict, have_cairo: bool = True) -> list:
    """What the dispatcher should run for a config."""
    if cfg["mode"] == "image" and cfg["image"] and valid_image(cfg["image"]):
        return ["swaybg", "-i", cfg["image"], "-m", "fill"]
    if cfg["mode"] == "live" and have_cairo:
        return ["saymy-live", "--daemon"]
    return ["saymy-sky"]
