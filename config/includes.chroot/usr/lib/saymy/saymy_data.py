"""Data wallet.

Counts bytes through the real network interfaces, keeps a daily ledger, and, once
the user tells us what their data costs, shows spend in their own currency.
No currency is assumed: set one with `saymy-data set-price 5000 UGX`
(price per GB) and it is used everywhere.

Honest scope for v0.1: totals per day (not per app). Per-app accounting needs
cgroup/nftables hooks and is planned for a later release.
"""
import datetime
import json
import os
import sys
from pathlib import Path

import saymy_i18n as i18n

SKIP_PREFIXES = ("lo", "docker", "veth", "br-", "virbr", "tun", "tap", "vmnet", "vboxnet", "wg")


def net_root() -> Path:
    return Path(os.environ.get("SAYMY_NET_ROOT", "/sys/class/net"))


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "saymy"


def ledger_path() -> Path:
    return data_dir() / "data.json"


def config_path() -> Path:
    return i18n.config_dir() / "data.json"


def read_counters(root: Path = None) -> dict:
    """{'rx': total_bytes_received, 'tx': total_bytes_sent} over real interfaces."""
    root = root or net_root()
    rx = tx = 0
    if root.is_dir():
        for dev in sorted(root.iterdir()):
            if dev.name.startswith(SKIP_PREFIXES):
                continue
            try:
                rx += int((dev / "statistics/rx_bytes").read_text())
                tx += int((dev / "statistics/tx_bytes").read_text())
            except (OSError, ValueError):
                continue
    return {"rx": rx, "tx": tx}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def record(now: datetime.date = None, counters: dict = None) -> dict:
    """Add the bytes used since the last call to today's total. Handles reboots
    (counters reset to zero) by treating the new value as fresh usage."""
    now = now or datetime.date.today()
    cur = counters or read_counters()
    ledger = _load(ledger_path(), {"last": None, "days": {}})
    last = ledger.get("last")
    d_rx = d_tx = 0
    if last:
        d_rx = cur["rx"] - last["rx"] if cur["rx"] >= last["rx"] else cur["rx"]
        d_tx = cur["tx"] - last["tx"] if cur["tx"] >= last["tx"] else cur["tx"]
    day = ledger["days"].setdefault(now.isoformat(), {"rx": 0, "tx": 0})
    day["rx"] += d_rx
    day["tx"] += d_tx
    ledger["last"] = cur
    # keep one year of history
    for key in sorted(ledger["days"])[:-366]:
        del ledger["days"][key]
    ledger_path().parent.mkdir(parents=True, exist_ok=True)
    ledger_path().write_text(json.dumps(ledger))
    return ledger


def human(n: int) -> str:
    for unit, size in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}" if unit != "KB" else f"{n / size:.0f} {unit}"
    return f"{n} B"


def price() -> dict:
    return _load(config_path(), {})


def cost_text(total_bytes: int) -> str:
    cfg = price()
    per_gb = cfg.get("price_per_gb")
    if not per_gb:
        return ""
    amount = total_bytes / 1e9 * per_gb
    return f"{cfg.get('currency', '')} {amount:,.0f}".strip()


def totals(ledger: dict, today: datetime.date = None) -> dict:
    today = today or datetime.date.today()
    out = {"today": 0, "week": 0, "month": 0}
    for key, v in ledger.get("days", {}).items():
        d = datetime.date.fromisoformat(key)
        used = v["rx"] + v["tx"]
        age = (today - d).days
        if age == 0:
            out["today"] += used
        if 0 <= age < 7:
            out["week"] += used
        if d.year == today.year and d.month == today.month:
            out["month"] += used
    return out


def today_text() -> str:
    t = totals(record())["today"]
    c = cost_text(t)
    return f"{human(t)} ({c})" if c else human(t)


def waybar() -> str:
    ledger = record()
    t = totals(ledger)
    text = "↓↑ " + human(t["today"])
    tip = "\n".join([
        f"{i18n.t('data.today')}: {human(t['today'])} {cost_text(t['today'])}".strip(),
        f"7d: {human(t['week'])} {cost_text(t['week'])}".strip(),
        f"{datetime.date.today():%B}: {human(t['month'])} {cost_text(t['month'])}".strip(),
    ])
    return json.dumps({"text": text, "tooltip": tip, "class": "data"}, ensure_ascii=False)


def set_price(per_gb: float, currency: str):
    cfg = price()
    cfg.update({"price_per_gb": per_gb, "currency": currency.upper()})
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg))


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "waybar":
        print(waybar())
    elif cmd == "set-price" and len(argv) == 3:
        set_price(float(argv[1]), argv[2])
        print(f"price set: {argv[1]} {argv[2].upper()} per GB")
    elif cmd == "status":
        print(today_text())
    else:
        print("usage: saymy-data [status|waybar|set-price <per-GB> <CURRENCY>]", file=sys.stderr)
        return 2
    return 0
