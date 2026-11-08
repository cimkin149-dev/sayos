"""SayMy Doctor: finds out what is wrong with a computer and explains it in plain language.

Every check calls a standard tool, tolerates it being missing, and returns Findings:
  level  ok | warn | bad
  title  one clear sentence
  detail what it means and what to do about it
  fix    optional {"label": ..., "cmd": [...]} the Doctor window offers as a button

Parsing is separated from running so it can be tested without hardware. SAYMY_DEMO=1 returns sample findings.
"""
import os
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path

import saymy_settings_backend as be

LEVELS = {"ok": 0, "warn": 1, "bad": 2}


@dataclass
class Finding:
    id: str
    level: str
    title: str
    detail: str = ""
    fix: dict = None

    def to_dict(self):
        return asdict(self)


# ------------------------------------------------------------------ parsers
def parse_ping(text: str):
    """Returns (packet_loss_percent, average_ms); None where absent."""
    loss = re.search(r"(\d+(?:\.\d+)?)% packet loss", text)
    avg = re.search(r"=\s*[\d.]+/([\d.]+)/", text)
    return (float(loss.group(1)) if loss else None, float(avg.group(1)) if avg else None)


def default_gateway(text: str):
    m = re.search(r"default via (\S+)", text)
    return m.group(1) if m else None


def parse_meminfo(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def parse_failed_units(text: str) -> list:
    return [ln.strip().lstrip("●* ").split()[0] for ln in text.splitlines() if ln.strip().lstrip("●* ")]


def parse_top_memory(text: str, n: int = 3) -> list:
    """`ps -eo comm,%mem --sort=-%mem` output -> [(name, percent)]"""
    rows = []
    for ln in text.splitlines()[1:]:
        parts = ln.rsplit(None, 1)
        if len(parts) == 2:
            try:
                rows.append((parts[0].strip(), float(parts[1])))
            except ValueError:
                pass
    return rows[:n]


def battery_health(root: Path = None):
    """Full-charge capacity compared with the design capacity, as a percentage, or None."""
    root = root or Path(os.environ.get("SAYMY_POWER_ROOT", "/sys/class/power_supply"))
    try:
        for dev in sorted(root.iterdir()):
            if (dev / "type").read_text().strip() != "Battery":
                continue
            for full, design in (("energy_full", "energy_full_design"), ("charge_full", "charge_full_design")):
                try:
                    f, d = int((dev / full).read_text()), int((dev / design).read_text())
                    if d > 0:
                        return round(100 * f / d)
                except (OSError, ValueError):
                    continue
    except OSError:
        pass
    return None


# ------------------------------------------------------------------ checks
def check_network() -> list:
    out = []
    ok, route = be.run(["ip", "route", "show", "default"])
    gw = default_gateway(route) if ok else None
    if not gw:
        return [Finding("net.none", "bad", "This computer is not connected to a network",
                        "Connect to Wi-Fi or plug in a cable. If Wi-Fi is on but nothing appears, the router may be off or out of range.",
                        {"label": "Open Network settings", "cmd": ["saymy-settings"]})]
    signal = next((w["signal"] for w in be.wifi_list() if w["connected"]), None)
    if signal is not None and signal < 40:
        out.append(Finding("net.signal", "warn", f"Weak Wi-Fi signal ({signal}%)",
                           "A weak signal is the most common cause of slow Wi-Fi. Move closer to the router, or away from walls and metal."))
    _, gw_out = be.run(["ping", "-c", "3", "-W", "2", "-q", gw], 12)
    loss, avg = parse_ping(gw_out)
    if loss is None or loss >= 100:
        out.append(Finding("net.router", "bad", "Your router is not answering",
                           "Restart the router, and check that you are still connected to the right network."))
        return out
    if loss > 5 or (avg or 0) > 80:
        out.append(Finding("net.router_slow", "warn", "Your router is responding slowly",
                           f"Round trip to the router: {avg:.0f} ms, {loss:.0f}% lost. This usually means Wi-Fi interference or too many devices. "
                           "Try the 5 GHz network, move closer, or restart the router."))
    _, net_out = be.run(["ping", "-c", "3", "-W", "2", "-q", "1.1.1.1"], 12)
    nloss, navg = parse_ping(net_out)
    if nloss is None or nloss >= 100:
        out.append(Finding("net.internet", "bad", "The router works, but the internet does not",
                           "The problem is beyond your computer: your internet provider may be down, or your data bundle may be finished."))
        return out
    ok_dns, _ = be.run(["getent", "hosts", "example.com"], 6)
    if not ok_dns:
        out.append(Finding("net.dns", "warn", "Website names are not resolving",
                           "You can reach the internet but not look up names (DNS). Restarting the router often fixes it."))
    elif nloss > 5 or (navg or 0) > 250:
        out.append(Finding("net.slow", "warn", "The internet connection is slow right now",
                           f"Round trip to the internet: {navg:.0f} ms, {nloss:.0f}% lost. Your provider may be congested. "
                           "Try again later, or pause large downloads and updates."))
    if not out:
        out.append(Finding("net.ok", "ok", "Your network looks healthy",
                           f"Router {avg:.0f} ms, internet {navg:.0f} ms" + (f", Wi-Fi signal {signal}%." if signal is not None else ".")))
    return out


def check_power() -> list:
    out = []
    import saymy_power
    st = saymy_power.read_state()
    if st["battery_pct"] is None:
        return []
    health = battery_health()
    if health is not None:
        if health < 60:
            out.append(Finding("pow.worn", "bad", f"The battery is worn out ({health}% of its original capacity)",
                               "It will not last long between charges, and a power cut will drain it fast. A replacement battery is the real fix."))
        elif health < 80:
            out.append(Finding("pow.aging", "warn", f"The battery is ageing ({health}% of its original capacity)",
                               "Expect shorter battery life than when it was new."))
    prof = be.profile_get()
    if prof == "performance" and st["ac"] is False:
        out.append(Finding("pow.profile", "warn", "Performance mode is on while running on battery",
                           "It uses the battery much faster. Balanced or Power saver will stretch it.",
                           {"label": "Switch to Balanced", "cmd": ["powerprofilesctl", "set", "balanced"]}))
    ok, active = be.run(["systemctl", "--user", "is-active", "saymy-power"])
    if active != "active" and not be.demo():
        out.append(Finding("pow.guard", "warn", "The power-cut guard is not running",
                           "Without it SayMy cannot protect your session when mains power drops.",
                           {"label": "Start it", "cmd": ["systemctl", "--user", "start", "saymy-power"]}))
    if not out:
        out.append(Finding("pow.ok", "ok", "Power and battery look fine",
                           f"Battery {st['battery_pct']}%" + (f", health {health}%" if health is not None else "") + "."))
    return out


def check_storage() -> list:
    du = shutil.disk_usage("/")
    free_pct = 100 * du.free / du.total
    if free_pct < 5:
        return [Finding("disk.full", "bad", f"The disk is almost full ({free_pct:.0f}% free)",
                        "Computers slow down and updates fail when the disk is full. Delete large files or clear the package cache.",
                        {"label": "Clear package cache", "cmd": ["pkexec", "apt-get", "clean"]})]
    if free_pct < 12:
        return [Finding("disk.low", "warn", f"Disk space is getting low ({free_pct:.0f}% free)",
                        "Free up space before it affects speed and updates.",
                        {"label": "Clear package cache", "cmd": ["pkexec", "apt-get", "clean"]})]
    return [Finding("disk.ok", "ok", "There is plenty of disk space", f"{du.free / 1e9:.0f} GB free of {du.total / 1e9:.0f} GB.")]


def check_memory() -> list:
    try:
        info = parse_meminfo(Path("/proc/meminfo").read_text())
        avail = 100 * info["MemAvailable"] / info["MemTotal"]
    except (OSError, KeyError, ZeroDivisionError):
        return []
    _, ps = be.run(["ps", "-eo", "comm,%mem", "--sort=-%mem"])
    top = ", ".join(f"{n} ({p:.0f}%)" for n, p in parse_top_memory(ps)) if ps else ""
    if avail < 8:
        return [Finding("mem.bad", "bad", f"The computer is almost out of memory ({avail:.0f}% free)",
                        "Close some apps or browser tabs. " + (f"Using most memory: {top}. " if top else "") + "Lite mode helps on small machines.")]
    if avail < 18:
        return [Finding("mem.low", "warn", f"Memory is getting tight ({avail:.0f}% free)",
                        (f"Using most memory: {top}. " if top else "") + "Closing browser tabs usually helps most.")]
    return [Finding("mem.ok", "ok", "Memory is fine", f"{avail:.0f}% available.")]


def check_services() -> list:
    ok, text = be.run(["systemctl", "--failed", "--no-legend", "--plain"])
    units = parse_failed_units(text) if ok else []
    if units:
        return [Finding("svc.failed", "warn", f"{len(units)} system service{'s' if len(units) > 1 else ''} failed to start",
                        "Failed: " + ", ".join(units[:5]) + ". Most are harmless, but if something misbehaves send this list to support.")]
    return [Finding("svc.ok", "ok", "All system services started normally")] if ok else []


def check_clock() -> list:
    ok, val = be.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    if ok and val == "no":
        return [Finding("time.sync", "warn", "The clock is not synchronised",
                        "A wrong clock makes websites show security errors. It corrects itself once you are online.",
                        {"label": "Sync the clock", "cmd": ["pkexec", "timedatectl", "set-ntp", "true"]})]
    return []


TOPICS = {"network": [check_network], "power": [check_power], "slow": [check_memory, check_storage, check_services],
          "all": [check_network, check_power, check_memory, check_storage, check_services, check_clock]}


def demo_findings() -> list:
    return [Finding("net.signal", "warn", "Weak Wi-Fi signal (31%)",
                    "A weak signal is the most common cause of slow Wi-Fi. Move closer to the router, or away from walls and metal."),
            Finding("net.router_slow", "warn", "Your router is responding slowly",
                    "Round trip to the router: 142 ms, 8% lost. This usually means Wi-Fi interference or too many devices.",
                    {"label": "Open Network settings", "cmd": ["saymy-settings"]}),
            Finding("pow.aging", "warn", "The battery is ageing (74% of its original capacity)", "Expect shorter battery life than when it was new."),
            Finding("mem.ok", "ok", "Memory is fine", "46% available."),
            Finding("disk.ok", "ok", "There is plenty of disk space", "212 GB free of 468 GB."),
            Finding("svc.ok", "ok", "All system services started normally")]


def diagnose(topic: str = "all") -> list:
    if be.demo():
        return demo_findings()
    findings = []
    for check in TOPICS.get(topic, TOPICS["all"]):
        try:
            findings += check()
        except Exception as exc:                      # a broken check must never hide the others
            findings.append(Finding(f"{check.__name__}.error", "warn", f"Could not run {check.__name__.replace('check_', '')} check", str(exc)))
    findings.sort(key=lambda f: -LEVELS[f.level])
    return findings


def headline(findings: list) -> str:
    bad = sum(f.level == "bad" for f in findings)
    warn = sum(f.level == "warn" for f in findings)
    if bad:
        return f"{bad} problem{'s' if bad > 1 else ''} found" + (f" and {warn} warning{'s' if warn > 1 else ''}" if warn else "")
    if warn:
        return f"{warn} thing{'s' if warn > 1 else ''} to look at"
    return "Everything looks healthy"


def text_report(findings: list) -> str:
    mark = {"ok": "OK     ", "warn": "WARNING", "bad": "PROBLEM"}
    lines = [headline(findings), ""]
    for f in findings:
        lines.append(f"[{mark[f.level]}] {f.title}")
        if f.detail:
            lines.append("          " + f.detail)
    return "\n".join(lines)


def main(argv):
    topic = argv[argv.index("--topic") + 1] if "--topic" in argv else "all"
    if "--text" in argv:
        print(text_report(diagnose(topic)))
        return 0
    return None
