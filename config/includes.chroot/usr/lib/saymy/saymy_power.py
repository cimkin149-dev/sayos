"""Power-cut resilience.

Watches mains power and the battery. When the grid drops the desktop protects
the session; when it returns, everything is restored. Every cut is written to a
local diary so people can see how often, and for how long, power failed.

State machine (pure functions, no side effects) lives in `events_for()`.
The loop in `watch()` turns events into actions: notifications, power profile,
screen dimming, and, if the battery runs low, suspend or hibernate.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import saymy_i18n as i18n

LOW_PCT = 20
CRITICAL_PCT = 10
HIBERNATE_PCT = 5
POLL_SECONDS = 10


def power_root() -> Path:
    return Path(os.environ.get("SAYMY_POWER_ROOT", "/sys/class/power_supply"))


def _read(p: Path, default=None):
    try:
        return p.read_text().strip()
    except OSError:
        return default


def read_state(root: Path = None) -> dict:
    """Snapshot of power: {'ac': bool|None, 'battery_pct': int|None, 'battery_status': str|None}.
    ac is None on machines that expose no mains supply (some tablets, VMs)."""
    root = root or power_root()
    ac = None
    pct = None
    status = None
    if root.is_dir():
        for dev in sorted(root.iterdir()):
            kind = _read(dev / "type", "")
            if kind in ("Mains", "USB", "USB_PD", "USB_DCP", "USB_C"):
                online = _read(dev / "online")
                if online is not None:
                    ac = bool(ac) or online == "1"
            elif kind == "Battery" and pct is None:
                cap = _read(dev / "capacity")
                if cap and cap.isdigit():
                    pct = int(cap)
                status = _read(dev / "status")
    if ac is None and status:
        ac = status in ("Charging", "Full")
    return {"ac": ac, "battery_pct": pct, "battery_status": status}


def events_for(prev: dict, cur: dict, flags: dict) -> list:
    """Decide what happened between two snapshots. `flags` remembers one-shot alerts
    and is mutated. Returns a list of event names."""
    ev = []
    if prev is not None and prev.get("ac") is True and cur.get("ac") is False:
        ev.append("power_cut")
        flags.clear()
    if prev is not None and prev.get("ac") is False and cur.get("ac") is True:
        ev.append("power_back")
        flags.clear()
    if cur.get("ac") is False and cur.get("battery_pct") is not None:
        pct = cur["battery_pct"]
        if pct <= HIBERNATE_PCT and not flags.get("hibernate"):
            flags["hibernate"] = flags["critical"] = flags["low"] = True
            ev.append("hibernate")
        elif pct <= CRITICAL_PCT and not flags.get("critical"):
            flags["critical"] = flags["low"] = True
            ev.append("critical")
        elif pct <= LOW_PCT and not flags.get("low"):
            flags["low"] = True
            ev.append("low")
    return ev


# ------------------------------------------------------------------ actions
def _run(cmd, dry, log):
    log.append(cmd)
    if dry:
        return
    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _notify(title, body, urgency, dry, log):
    _run(["notify-send", "-a", "SayMy Power", "-i", "saymy", "-u", urgency, title, body], dry, log)


def has_swap() -> bool:
    try:
        lines = Path("/proc/swaps").read_text().strip().splitlines()
        return len(lines) > 1 and Path("/sys/power/disk").exists()
    except OSError:
        return False


def diary_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "saymy" / "power-log.jsonl"


def diary(entry: dict, dry=False):
    if dry:
        return
    p = diary_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def apply(event: str, cur: dict, dry: bool = False) -> list:
    """Perform the actions for one event. Returns the list of commands (for tests)."""
    log = []
    pct = cur.get("battery_pct")
    if event == "power_cut":
        _run(["saymy-sound", "play", "power-cut"], dry, log)
        _notify(i18n.t("power.cut"), i18n.t("power.cut.body"), "low", dry, log)
        _run(["powerprofilesctl", "set", "power-saver"], dry, log)
        _run(["brightnessctl", "--save", "set", "40%"], dry, log)
        _run(["sync"], dry, log)
        diary({"event": "cut", "ts": int(time.time()), "battery_pct": pct}, dry)
    elif event == "power_back":
        _run(["saymy-sound", "play", "power-back"], dry, log)
        _notify(i18n.t("power.back"), "", "low", dry, log)
        _run(["powerprofilesctl", "set", "balanced"], dry, log)
        _run(["brightnessctl", "--restore"], dry, log)
        diary({"event": "back", "ts": int(time.time()), "battery_pct": pct}, dry)
    elif event == "low":
        _run(["saymy-sound", "play", "battery-low"], dry, log)
        _notify(i18n.t("power.low", pct=pct), "", "low", dry, log)
    elif event == "critical":
        _notify(i18n.t("power.critical", pct=pct), "", "critical", dry, log)
        _run(["sync"], dry, log)
        _run(["saymy-session-save"], dry, log)
    elif event == "hibernate":
        _run(["sync"], dry, log)
        _run(["saymy-session-save"], dry, log)
        _run(["systemctl", "hibernate" if has_swap() else "suspend"], dry, log)
    return log


def diary_summary(days: int = 30) -> dict:
    """Total number and duration of power cuts in the last `days` days."""
    cuts, total, start = 0, 0, None
    horizon = time.time() - days * 86400
    try:
        for line in diary_path().read_text().splitlines():
            e = json.loads(line)
            if e["ts"] < horizon:
                continue
            if e["event"] == "cut":
                start = e["ts"]
                cuts += 1
            elif e["event"] == "back" and start:
                total += e["ts"] - start
                start = None
    except (OSError, ValueError, KeyError):
        pass
    return {"cuts": cuts, "seconds": total}


def watch(once=False, dry=False):
    prev, flags = None, {}
    while True:
        cur = read_state()
        for ev in events_for(prev, cur, flags):
            if dry:
                print(json.dumps({"event": ev, "state": cur, "actions": apply(ev, cur, dry=True)}))
            else:
                apply(ev, cur)
        prev = cur
        if once:
            return 0
        time.sleep(POLL_SECONDS)


def main(argv):
    if "--summary" in argv:
        print(json.dumps(diary_summary()))
        return 0
    if "--state" in argv:
        print(json.dumps(read_state()))
        return 0
    return watch(once="--once" in argv, dry="--dry-run" in argv)
