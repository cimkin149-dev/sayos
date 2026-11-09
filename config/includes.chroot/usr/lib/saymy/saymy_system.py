"""Administrator actions for SayMy Settings: users, software updates, offline update bundles.

Everything that needs root goes through sudo with a graphical password prompt (saymy-askpass), because the
SayMy session has no polkit agent. Pure logic (validation, parsing, manifests) is separated from the parts that
call tools, so it can be tested without root. Functions that run commands accept a `runner` for tests.
"""
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import time
from pathlib import Path

import saymy_settings_backend as be

HELPER = "/usr/lib/saymy/saymy-user-helper"
UPDATE_HELPER = "/usr/lib/saymy/saymy-update-helper"
ASKPASS = "/usr/bin/saymy-askpass"
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
RESERVED = {"root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news", "uucp", "proxy", "www-data",
            "backup", "list", "irc", "gnats", "nobody", "sddm", "saymy", "admin", "administrator", "guest", "user",
            "systemd-network", "messagebus", "avahi", "polkitd", "sshd"}
UPGRADE_RE = re.compile(r"^(?P<name>[^/\s]+)/(?P<suite>\S+)\s+(?P<new>\S+)\s+\S+\s+\[upgradable from:\s*(?P<old>[^\]]+)\]")


# ------------------------------------------------------------------ elevation
def elevate(cmd: list) -> list:
    """Wrap a command so it runs as root, asking for the user's password in a SayMy window."""
    return ["env", f"SUDO_ASKPASS={ASKPASS}", "sudo", "-A", "-p", "SayMy needs your password to continue", *cmd]


def _run(cmd, runner=None, stdin=None, timeout=900):
    runner = runner or subprocess.run
    try:
        p = runner(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


# ------------------------------------------------------------------ users: validation
def valid_username(name: str) -> bool:
    return bool(USERNAME_RE.match(name or "")) and name not in RESERVED


def clean_fullname(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f:,]", "", name or "").strip()[:60]


def valid_password(pw: str) -> bool:
    return bool(pw) and len(pw) >= 6 and "\n" not in pw and "\r" not in pw and "\x00" not in pw


def list_users(passwd_file="/etc/passwd", group_file="/etc/group") -> list:
    """Real people (UID 1000 to 59999) with an admin flag (member of the sudo group)."""
    admins = set()
    try:
        for line in Path(group_file).read_text().splitlines():
            f = line.split(":")
            if len(f) >= 4 and f[0] == "sudo":
                admins = set(filter(None, f[3].split(",")))
    except OSError:
        pass
    users = []
    try:
        for line in Path(passwd_file).read_text().splitlines():
            f = line.split(":")
            if len(f) >= 7 and f[2].isdigit() and 1000 <= int(f[2]) < 60000 and f[0] != "nobody":
                users.append({"name": f[0], "uid": int(f[2]), "fullname": f[4].split(",")[0], "admin": f[0] in admins})
    except OSError:
        pass
    return users


def current_user() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "")


def demo_users() -> list:
    return [{"name": "steven", "uid": 1000, "fullname": "Steven", "admin": True},
            {"name": "grace", "uid": 1001, "fullname": "Grace", "admin": False}]


# ------------------------------------------------------------------ users: actions (root helper does the work)
def helper(sub: str, *args, stdin=None, runner=None):
    return _run(elevate([HELPER, sub, *args]), runner, stdin=stdin)


def add_user(username, fullname, password, admin=False, runner=None):
    if not valid_username(username):
        raise ValueError("Use 1 to 31 lowercase letters, digits, - or _, starting with a letter. Some names are reserved.")
    if not valid_password(password):
        raise ValueError("The password must be at least 6 characters.")
    return helper("add", username, clean_fullname(fullname) or username, "--admin" if admin else "--standard",
                  stdin=password + "\n", runner=runner)


def set_password(username, password, runner=None):
    if not valid_password(password):
        raise ValueError("The password must be at least 6 characters.")
    return helper("passwd", username, stdin=password + "\n", runner=runner)


def set_admin(username, on: bool, runner=None):
    return helper("admin", username, "on" if on else "off", runner=runner)


def remove_user(username, runner=None):
    return helper("delete", username, runner=runner)


# ------------------------------------------------------------------ updates
def parse_upgradable(text: str) -> list:
    """Parse `apt list --upgradable`."""
    out = []
    for line in text.splitlines():
        m = UPGRADE_RE.match(line)
        if m:
            d = m.groupdict()
            d["security"] = "security" in d["suite"]
            out.append(d)
    return sorted(out, key=lambda p: (not p["security"], p["name"]))


def check_updates(runner=None) -> list:
    if be.demo():
        return [{"name": "firefox-esr", "suite": "trixie-security", "new": "140.4.0esr-1", "old": "140.3.1esr-1", "security": True},
                {"name": "linux-image-amd64", "suite": "trixie-security", "new": "6.12.57-1", "old": "6.12.48-1", "security": True},
                {"name": "labwc", "suite": "trixie", "new": "0.8.4-1", "old": "0.8.2-1", "security": False}]
    ok, out = _run(["apt", "list", "--upgradable"], runner, timeout=60)
    return parse_upgradable(out) if ok else []


def lists_age_hours(path="/var/lib/apt/periodic/update-success-stamp"):
    try:
        return round((time.time() - os.path.getmtime(path)) / 3600)
    except OSError:
        return None


def update_lists(runner=None):
    return _run(elevate(["apt-get", "update"]), runner, timeout=300)


def install_updates(on_line=None, runner=None):
    """Install all updates. Streams output lines to on_line. Returns True on success."""
    cmd = elevate(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "upgrade"])
    if runner:
        ok, out = _run(cmd, runner)
        for ln in out.splitlines():
            on_line and on_line(ln)
        return ok
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as exc:
        on_line and on_line(str(exc))
        return False
    for ln in p.stdout:
        on_line and on_line(ln.rstrip())
    return p.wait() == 0


# ------------------------------------------------------------------ safe updates (with Undo)
def _stream(cmd, on_line=None, runner=None):
    """Run the root helper, forward its lines, and return (ok, RESULT dict)."""
    result, ok = {}, False
    if runner:
        ok0, text = _run(cmd, runner)
        lines, ok = text.splitlines(), ok0
    else:
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except OSError as exc:
            on_line and on_line(str(exc))
            return False, {"ok": False, "error": str(exc)}
        lines = (ln.rstrip() for ln in p.stdout)
    for ln in lines:
        if ln.startswith("RESULT: "):
            try:
                result = json.loads(ln[8:])
            except ValueError:
                pass
        elif on_line:
            on_line(ln[10:] if ln.startswith("PROGRESS: ") else ln)
    if not runner:
        ok = p.wait() == 0
    return ok and result.get("ok", True), result


def safe_apply(on_line=None, bundle=None, runner=None):
    args = ["apply-bundle", bundle] if bundle else ["apply"]
    return _stream(elevate([UPDATE_HELPER, *args]), on_line, runner)


def safe_undo(txn_id, on_line=None, runner=None):
    return _stream(elevate([UPDATE_HELPER, "undo", txn_id]), on_line, runner)


def undo_list() -> list:
    import saymy_safeupdate as su
    if be.demo():
        return [{"id": "20261108-170500", "when": "08 Nov 2026, 17:05", "count": 14, "status": "installed", "ok": True,
                 "new_failures": ["bluetooth.service"], "kernel": False, "undoable": True},
                {"id": "20261101-090200", "when": "01 Nov 2026, 09:02", "count": 6, "status": "installed", "ok": True,
                 "new_failures": [], "kernel": True, "undoable": True}]
    return su.summary(su.load_journal())


def update_blockers() -> list:
    """Messages that should stop the Install button right now (power, disk, half-finished installs)."""
    import saymy_power
    import saymy_safeupdate as su
    if be.demo():
        return []
    def sh(cmd, cwd=None):
        ok, text = _run(cmd)
        return (0 if ok else 1), text

    return [p["message"] for p in su.precheck(sh, saymy_power.read_state(), shutil.disk_usage("/var/lib").free) if p["blocking"]]


# ------------------------------------------------------------------ offline update bundles
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def deb_info(path: Path) -> dict:
    m = re.match(r"^([^_]+)_([^_]+)_", path.name)
    return {"file": path.name, "name": m.group(1) if m else path.stem, "version": m.group(2).replace("%3a", ":") if m else "",
            "sha256": sha256_file(path)}


def build_manifest(folder: Path) -> dict:
    debs = sorted(folder.glob("*.deb"))
    return {"format": 1, "created": int(time.time()), "release": "SayMy OS 0.1",
            "packages": [deb_info(d) for d in debs]}


def make_bundle(dest, archives="/var/cache/apt/archives", runner=None):
    """On a computer WITH internet: download all pending updates and gather them in `dest` with a manifest."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ok, out = _run(elevate(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "--download-only", "upgrade"]), runner)
    if not ok:
        return False, out
    n = 0
    for deb in Path(archives).glob("*.deb"):
        shutil.copy2(deb, dest / deb.name)
        n += 1
    manifest = build_manifest(dest)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return True, f"Bundle ready: {n} packages in {dest}"


def verify_bundle(folder) -> list:
    """Return a list of problems (empty means the bundle matches its manifest exactly)."""
    folder = Path(folder)
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError):
        return ["manifest.json is missing or unreadable"]
    problems, listed = [], set()
    for p in manifest.get("packages", []):
        f = folder / p["file"]
        listed.add(p["file"])
        if p["file"] != os.path.basename(p["file"]):
            problems.append(f"unsafe file name {p['file']!r}")
        elif not f.exists():
            problems.append(f"{p['file']} is missing")
        elif sha256_file(f) != p["sha256"]:
            problems.append(f"{p['file']} does not match its checksum (damaged or changed)")
    for extra in sorted(set(x.name for x in folder.glob("*.deb")) - listed):
        problems.append(f"{extra} is not in the manifest")
    if not manifest.get("packages"):
        problems.append("the bundle contains no packages")
    return problems


def install_bundle(folder, runner=None):
    """On an offline computer: install a verified bundle. Refuses to install anything that fails verification."""
    folder = Path(folder)
    problems = verify_bundle(folder)
    if problems:
        return False, "Not installed. " + "; ".join(problems)
    debs = [str(folder / p["file"]) for p in json.loads((folder / "manifest.json").read_text())["packages"]]
    ok, out = _run(elevate(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "--no-download", *debs]), runner)
    return ok, out[-2000:]
