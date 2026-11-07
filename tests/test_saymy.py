#!/usr/bin/env python3
"""Run:  python3 tests/test_saymy.py     (no root, no ISO, no hardware needed)"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INC = ROOT / "config/includes.chroot"
LIB = INC / "usr/lib/saymy"
BIN = INC / "usr/bin"
SHARE = INC / "usr/share/saymy"

os.environ["SAYMY_SHARE"] = str(SHARE)
os.environ["SAYMY_LIB"] = str(LIB)
sys.path.insert(0, str(LIB))

import saymy_i18n as i18n      # noqa: E402
import saymy_say as say        # noqa: E402
import saymy_power as power    # noqa: E402
import saymy_data as data      # noqa: E402


class SayBar(unittest.TestCase):
    def test_english_open(self):
        r = say.match("Open Firefox", "en")
        self.assertEqual(r[0], "open_app")
        self.assertEqual(r[1]["app"], "firefox")

    def test_swahili_and_english_mix(self):
        # The user's language is English but they speak Kiswahili: still understood.
        self.assertEqual(say.match("fungua firefox", "en")[0], "open_app")
        self.assertEqual(say.match("funga skrini", "en")[0], "lock")
        self.assertEqual(say.match("ongeza sauti", "en")[0], "volume_up")

    def test_exact_beats_slot(self):
        self.assertEqual(say.match("search for cats", "en")[1]["query"], "cats")

    def test_unknown(self):
        self.assertIsNone(say.match("blorp the zibble", "en"))
        r = say.handle("blorp the zibble", "en")
        self.assertIn("understand", r.message)

    def test_calc(self):
        self.assertEqual(say.safe_calc("12*8"), 96)
        self.assertEqual(say.safe_calc("12 x 8"), 96)
        self.assertEqual(say.safe_calc("10 divided by 4"), 2.5)
        self.assertEqual(say.safe_calc("2^10"), 1024)
        self.assertEqual(say.safe_calc("1,000 + 500"), 1500)

    def test_calc_rejects_code(self):
        for bad in ("__import__('os').system('id')", "open('/etc/passwd')", "1 if 1 else 2", "2**99999999"):
            with self.assertRaises(ValueError):
                say.safe_calc(bad)

    def test_calc_via_handle(self):
        r = say.handle("calculate 12*8", "en")
        self.assertIn("96", r.message)
        r = say.handle("hesabu 12*8", "sw")
        self.assertIn("96", r.message)
        r = say.handle("calculate __import__('os')", "en")
        self.assertIn("can’t calculate", r.message)

    def test_reply_language_follows_command(self):
        r = say.handle("saa", "en")           # Swahili command, English UI
        self.assertTrue(r.message.startswith("Saa ni"))

    def test_app_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "firefox-esr.desktop").write_text("[Desktop Entry]\nName=Firefox ESR\nExec=firefox-esr %u\n")
            (Path(d) / "pcmanfm.desktop").write_text("[Desktop Entry]\nName=File Manager PCManFM\nExec=pcmanfm\n")
            (Path(d) / "hidden.desktop").write_text("[Desktop Entry]\nName=Firefox Secret\nNoDisplay=true\nExec=x\n")
            os.environ["SAYMY_APP_DIRS"] = d
            try:
                self.assertEqual(say.find_app("firefox"), "firefox-esr.desktop")
                self.assertEqual(say.find_app("files"), "pcmanfm.desktop")
                self.assertIsNone(say.find_app("nonexistent"))
                r = say.handle("open firefox", "en")
                self.assertEqual(r.exec, ["gtk-launch", "firefox-esr.desktop"])
                r = say.handle("open nonexistent", "en")
                self.assertIsNone(r.exec)
                self.assertIn("couldn’t find", r.message)
            finally:
                del os.environ["SAYMY_APP_DIRS"]

    def test_search_url_is_encoded(self):
        r = say.handle("search for cats & dogs", "en")
        self.assertEqual(r.exec[0], "xdg-open")
        self.assertIn("cats+%26+dogs", r.exec[1])

    def test_cli_dry_run(self):
        out = subprocess.run([str(BIN / "saymy-say"), "--dry-run", "lock"], capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout)["exec"], ["saymy-lock"])

    def test_every_catalog_key_used_exists_in_english(self):
        en = json.loads((SHARE / "i18n/en.json").read_text())
        for f in (SHARE / "i18n").glob("*.json"):
            extra = set(json.loads(f.read_text())) - set(en)
            self.assertFalse(extra, f"{f.name} has keys English lacks: {extra}")

    def test_every_intent_file_valid(self):
        for f in (SHARE / "say/intents").glob("*.json"):
            d = json.loads(f.read_text())
            for intent in d["intents"]:
                self.assertTrue(intent["patterns"], f"{f.name}:{intent['id']} has no patterns")


class PowerCut(unittest.TestCase):
    def make(self, ac, pct, status="Discharging"):
        d = tempfile.mkdtemp()
        (Path(d) / "AC").mkdir()
        (Path(d) / "AC/type").write_text("Mains")
        (Path(d) / "AC/online").write_text("1" if ac else "0")
        (Path(d) / "BAT0").mkdir()
        (Path(d) / "BAT0/type").write_text("Battery")
        (Path(d) / "BAT0/capacity").write_text(str(pct))
        (Path(d) / "BAT0/status").write_text(status)
        return Path(d)

    def test_read_state(self):
        st = power.read_state(self.make(True, 80, "Charging"))
        self.assertEqual(st, {"ac": True, "battery_pct": 80, "battery_status": "Charging"})
        st = power.read_state(self.make(False, 33))
        self.assertFalse(st["ac"])

    def test_no_power_supply_dir(self):
        st = power.read_state(Path("/nonexistent"))
        self.assertEqual(st, {"ac": None, "battery_pct": None, "battery_status": None})

    def test_cut_and_back(self):
        flags = {}
        on = {"ac": True, "battery_pct": 90}
        off = {"ac": False, "battery_pct": 90}
        self.assertEqual(power.events_for(on, off, flags), ["power_cut"])
        self.assertEqual(power.events_for(off, on, flags), ["power_back"])
        self.assertEqual(power.events_for(on, on, flags), [])

    def test_alerts_fire_once_in_order(self):
        flags = {}
        off = lambda p: {"ac": False, "battery_pct": p}
        seq = []
        prev = off(100)
        for p in (50, 20, 19, 10, 9, 5, 4, 3):
            cur = off(p)
            seq += power.events_for(prev, cur, flags)
            prev = cur
        self.assertEqual(seq, ["low", "critical", "hibernate"])

    def test_actions_dry(self):
        log = power.apply("power_cut", {"battery_pct": 90}, dry=True)
        flat = [" ".join(c) for c in log]
        self.assertTrue(any("powerprofilesctl set power-saver" in c for c in flat))
        self.assertTrue(any("brightnessctl --save" in c for c in flat))
        log = power.apply("power_back", {"battery_pct": 90}, dry=True)
        self.assertTrue(any("brightnessctl --restore" in " ".join(c) for c in log))

    def test_diary_summary(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["XDG_DATA_HOME"] = d
            try:
                import time
                now = int(time.time())
                power.diary({"event": "cut", "ts": now - 3600})
                power.diary({"event": "back", "ts": now - 1800})
                power.diary({"event": "cut", "ts": now - 600})
                power.diary({"event": "back", "ts": now - 300})
                s = power.diary_summary()
                self.assertEqual(s["cuts"], 2)
                self.assertEqual(s["seconds"], 1800 + 300)
            finally:
                del os.environ["XDG_DATA_HOME"]


class DataWallet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = self.tmp
        os.environ["XDG_CONFIG_HOME"] = self.tmp + "/cfg"

    def tearDown(self):
        del os.environ["XDG_DATA_HOME"], os.environ["XDG_CONFIG_HOME"]

    def test_counters_skip_virtual(self):
        root = Path(tempfile.mkdtemp())
        for name, rx, tx in (("wlan0", 1000, 500), ("lo", 99999, 99999), ("docker0", 5000, 5000)):
            (root / name / "statistics").mkdir(parents=True)
            (root / name / "statistics/rx_bytes").write_text(str(rx))
            (root / name / "statistics/tx_bytes").write_text(str(tx))
        self.assertEqual(data.read_counters(root), {"rx": 1000, "tx": 500})

    def test_record_and_reboot(self):
        day = datetime.date(2026, 11, 7)
        data.record(day, {"rx": 1000, "tx": 0})
        led = data.record(day, {"rx": 3000, "tx": 500})
        self.assertEqual(led["days"]["2026-11-07"], {"rx": 2000, "tx": 500})
        # reboot: counters restart from a small number
        led = data.record(day, {"rx": 100, "tx": 50})
        self.assertEqual(led["days"]["2026-11-07"], {"rx": 2100, "tx": 550})

    def test_totals_and_cost(self):
        ledger = {"days": {"2026-11-07": {"rx": 400_000_000, "tx": 100_000_000},
                           "2026-11-03": {"rx": 1_000_000_000, "tx": 0},
                           "2026-10-01": {"rx": 2_000_000_000, "tx": 0}}}
        t = data.totals(ledger, datetime.date(2026, 11, 7))
        self.assertEqual(t["today"], 500_000_000)
        self.assertEqual(t["week"], 1_500_000_000)
        self.assertEqual(t["month"], 1_500_000_000)
        self.assertEqual(data.cost_text(500_000_000), "")        # no price set: no assumed currency
        data.set_price(5000, "ugx")
        self.assertEqual(data.cost_text(500_000_000), "UGX 2,500")

    def test_human(self):
        self.assertEqual(data.human(1_500_000), "1.5 MB")
        self.assertEqual(data.human(2_300_000_000), "2.3 GB")


class Sky(unittest.TestCase):
    def phase(self, hour):
        env = dict(os.environ, FAKE_HOUR=str(hour))
        return subprocess.run([str(BIN / "saymy-sky"), "--phase"], capture_output=True, text=True, env=env).stdout.strip()

    def test_phases(self):
        expect = {4: "night", 5: "sunrise", 7: "sunrise", 8: "day", 16: "day", 17: "dusk", 19: "dusk", 20: "night", 0: "night", "08": "day", "09": "day"}
        for h, p in expect.items():
            self.assertEqual(self.phase(h), p, f"hour {h}")

    def test_all_wallpapers_exist(self):
        for p in ("sunrise", "day", "dusk", "night"):
            self.assertTrue((SHARE / f"wallpapers/saymy-{p}.jpg").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
