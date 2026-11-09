"""Safe Updates: updates that cannot quietly break your computer, with one-tap Undo.

What v0.1 does (see docs/SAFE-UPDATES.md for the full design and the roadmap):
  1. Prechecks   refuse to start when power is unsafe (on battery below 50%), disk space is short (< 2 GB free),
                 or a previous install is half finished (dpkg --audit / apt-get check).
  2. Keep old    before changing anything, rebuild a .deb of the CURRENTLY installed version of every package that
                 is about to be upgraded (dpkg-repack, which also keeps your edited settings) and checksum it.
  3. Upgrade     run the upgrade, then check dpkg is consistent.
  4. Health      compare failed system services before and after; any NEW failure is reported with an Undo offer.
  5. Undo        reinstall the kept versions (downgrade) and hold those packages so they are not upgraded again
                 until you choose to install updates again. The last 3 updates stay undoable.

Everything that touches the system goes through `sh(cmd, cwd=None) -> (returncode, output)` so the logic can be
tested with a fake. The root helper (saymy-update-helper) supplies the real one.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

KEEP = 3
MIN_FREE = 2 * 1024 ** 3
MIN_BATTERY = 50


def journal_dir() -> Path:
    return Path(os.environ.get("SAYMY_UNDO_DIR", "/var/lib/saymy/updates"))


def real_sh(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=3600)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


# ------------------------------------------------------------------ journal
def load_journal(d: Path = None) -> list:
    try:
        return json.loads((Path(d or journal_dir()) / "journal.json").read_text())
    except (OSError, ValueError):
        return []


def save_journal(entries: list, d: Path = None):
    d = Path(d or journal_dir())
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "journal.json.tmp"
    tmp.write_text(json.dumps(entries, indent=1))
    tmp.replace(d / "journal.json")


def prune(entries: list, d: Path = None, keep: int = KEEP) -> list:
    d = Path(d or journal_dir())
    for old in entries[:-keep] if len(entries) > keep else []:
        shutil.rmtree(d / old["id"], ignore_errors=True)
        old["pruned"] = True
    return [e for e in entries if not e.get("pruned")]


# ------------------------------------------------------------------ checks
def precheck(sh, power: dict, free_bytes: int) -> list:
    """Return [{'blocking': bool, 'message': str}]. Empty list means safe to start."""
    out = []
    if power.get("ac") is False and power.get("battery_pct") is not None and power["battery_pct"] < MIN_BATTERY:
        out.append({"blocking": True, "message": f"Plug in the charger first. The battery is at {power['battery_pct']}% and updates need mains power or at least {MIN_BATTERY}%."})
    if free_bytes < MIN_FREE:
        out.append({"blocking": True, "message": f"Not enough free disk space ({free_bytes / 1e9:.1f} GB free, 2 GB needed). Free some space first."})
    rc, text = sh(["dpkg", "--audit"])
    if text.strip():
        out.append({"blocking": True, "message": "A previous installation did not finish. Run “sudo dpkg --configure -a” or ask for help before updating."})
    rc, _ = sh(["apt-get", "check"])
    if rc != 0:
        out.append({"blocking": True, "message": "The package database has problems (apt-get check failed). Updating now could make it worse."})
    return out


def failed_units(sh) -> set:
    rc, text = sh(["systemctl", "--failed", "--no-legend", "--plain"])
    if rc != 0:
        return set()
    return {ln.strip().lstrip("●* ").split()[0] for ln in text.splitlines() if ln.strip().lstrip("●* ")}


def installed_version(sh, name: str):
    rc, out = sh(["dpkg-query", "-W", "-f=${Status}|${Version}|${Architecture}", name])
    if rc != 0:
        return None
    status, version, arch = (out.split("|") + ["", ""])[:3]
    return (version, arch) if "install ok installed" in status else None


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ keep the old versions
def snapshot(sh, names: list, dest: Path):
    """Rebuild a .deb of each installed package. Returns (saved, skipped)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    saved, skipped = [], []
    for name in names:
        info = installed_version(sh, name)
        if not info:
            skipped.append({"name": name, "reason": "new package, nothing to keep"})
            continue
        before = set(dest.glob("*.deb"))
        rc, out = sh(["dpkg-repack", name], cwd=str(dest))
        made = sorted(set(dest.glob(f"{name}_*.deb")) - before, key=lambda p: p.stat().st_mtime)
        if rc != 0 or not made:
            skipped.append({"name": name, "reason": (out.strip().splitlines() or ["could not keep the old version"])[-1]})
            continue
        f = made[-1]
        saved.append({"name": name, "old": info[0], "file": f.name, "sha256": sha256_file(f)})
    return saved, skipped


# ------------------------------------------------------------------ apply
def apply_updates(sh, names: list, upgrade_cmd: list, power: dict, free_bytes: int, on_line=print,
                  d: Path = None, now=None) -> dict:
    d = Path(d or journal_dir())
    say = lambda m: on_line("PROGRESS: " + m)
    say("Checking that it is safe to update…")
    problems = precheck(sh, power, free_bytes)
    blocking = [p for p in problems if p["blocking"]]
    if blocking:
        for p in blocking:
            say(p["message"])
        return {"ok": False, "stage": "precheck", "problems": [p["message"] for p in blocking]}
    release_holds(sh, d, on_line)
    before_failed = failed_units(sh)
    txn_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(now or time.time()))
    say(f"Keeping the current version of {len(names)} packages so the update can be undone…")
    saved, skipped = snapshot(sh, names, d / txn_id)
    say(f"Kept {len(saved)} package versions" + (f"; {len(skipped)} are new and need no copy." if skipped else "."))
    say("Installing updates. Please keep the computer on and plugged in…")
    rc, out = sh(upgrade_cmd)
    for ln in out.splitlines()[-200:]:
        on_line(ln)
    rc2, audit = sh(["dpkg", "--audit"])
    consistent = rc == 0 and not audit.strip()
    after_failed = failed_units(sh)
    new_failures = sorted(after_failed - before_failed)
    entry = {"id": txn_id, "created": int(now or time.time()), "status": "installed", "ok": consistent,
             "packages": saved, "new_packages": [s["name"] for s in skipped], "new_failures": new_failures,
             "kernel": any(n.startswith("linux-image") for n in names), "held": []}
    entries = prune(load_journal(d) + [entry], d)
    save_journal(entries, d)
    if not consistent:
        say("The update did not finish cleanly. Your previous versions are kept: you can Undo it.")
    elif new_failures:
        say("Updated, but these services failed afterwards: " + ", ".join(new_failures) + ". You can Undo this update.")
    else:
        say("Updated successfully. All services are healthy.")
    return {"ok": consistent, "stage": "done", "txn": txn_id, "new_failures": new_failures,
            "kept": len(saved), "kernel": entry["kernel"]}


# ------------------------------------------------------------------ undo
def undo(sh, txn_id: str, on_line=print, d: Path = None) -> dict:
    d = Path(d or journal_dir())
    say = lambda m: on_line("PROGRESS: " + m)
    entries = load_journal(d)
    txn = next((e for e in entries if e["id"] == txn_id), None)
    if not txn:
        return {"ok": False, "error": "That update is no longer in the undo list."}
    if txn["status"] == "undone":
        return {"ok": False, "error": "That update was already undone."}
    files = []
    for p in txn["packages"]:
        f = d / txn_id / p["file"]
        if not f.exists() or sha256_file(f) != p["sha256"]:
            return {"ok": False, "error": f"The kept copy of {p['name']} is missing or damaged, so this update cannot be undone safely."}
        files.append(str(f))
    if not files:
        return {"ok": False, "error": "Nothing was kept for this update."}
    say(f"Restoring {len(files)} packages to their previous versions…")
    rc, out = sh(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "--allow-downgrades", "--no-download", *files])
    for ln in out.splitlines()[-100:]:
        on_line(ln)
    if rc != 0:
        return {"ok": False, "error": "The restore did not finish. Your computer may be partly restored; try again or ask for help."}
    names = [p["name"] for p in txn["packages"]]
    sh(["apt-mark", "hold", *names])
    txn["status"], txn["held"] = "undone", names
    save_journal(entries, d)
    say("Restored. These packages are held back so they are not updated again until you choose to install updates." +
        (" Restart the computer to use the previous kernel." if txn.get("kernel") else ""))
    return {"ok": True, "restored": len(files), "kernel": txn.get("kernel", False)}


def release_holds(sh, d: Path = None, on_line=print):
    d = Path(d or journal_dir())
    entries = load_journal(d)
    names = sorted({n for e in entries for n in e.get("held", [])})
    if names:
        sh(["apt-mark", "unhold", *names])
        for e in entries:
            e["held"] = []
        save_journal(entries, d)
        on_line("PROGRESS: Released the packages that were held back after the last undo.")
    return names


def summary(entries: list) -> list:
    """What the Settings panel shows: newest first."""
    out = []
    for e in reversed(entries):
        out.append({"id": e["id"], "when": time.strftime("%d %b %Y, %H:%M", time.localtime(e["created"])),
                    "count": len(e["packages"]), "status": e["status"], "ok": e["ok"], "new_failures": e["new_failures"],
                    "kernel": e["kernel"], "undoable": e["status"] == "installed" and bool(e["packages"])})
    return out
