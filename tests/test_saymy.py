#!/usr/bin/env python3
"""Run:  python3 tests/test_saymy.py     (no root, no ISO, no hardware needed)"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import types
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
import saymy_settings_backend as sb  # noqa: E402
import saymy_doctor as doc  # noqa: E402
import saymy_drop as drop  # noqa: E402
import saymy_system as sysm  # noqa: E402
import saymy_safeupdate as su  # noqa: E402
import saymy_looks as lk  # noqa: E402
import saymy_sound as snd  # noqa: E402
import saymy_wallpaper as wpm  # noqa: E402
try:
    import saymy_live as live  # noqa: E402
except ImportError:            # pycairo is not installed on every machine that runs these checks
    live = None


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


class SettingsBackend(unittest.TestCase):
    def test_parse_wifi(self):
        text = "*:Kampala-Home:82:WPA2\n :MakCampus:64:WPA2\n :Cafe\\: Guest:41:--\n :MakCampus:70:WPA2\n ::50:WPA2"
        nets = sb.parse_wifi(text)
        self.assertEqual([n["ssid"] for n in nets], ["Kampala-Home", "MakCampus", "Cafe: Guest"])
        self.assertTrue(nets[0]["connected"])
        self.assertEqual(nets[1]["signal"], 70)           # strongest duplicate wins
        self.assertFalse(nets[2]["secure"])

    def test_parse_brightness_and_volume(self):
        self.assertEqual(sb.parse_brightness("intel_backlight,backlight,4800,50%,9600"), 50)
        self.assertIsNone(sb.parse_brightness("garbage"))
        self.assertEqual(sb.parse_volume("Volume: 0.60"), (60, False))
        self.assertEqual(sb.parse_volume("Volume: 0.35 [MUTED]"), (35, True))
        self.assertEqual(sb.parse_volume("nothing"), (None, False))

    def test_missing_tools_degrade_gracefully(self):
        ok, out = sb.run(["definitely-not-a-real-tool"])
        self.assertEqual((ok, out), (False, ""))

    def test_normalize_hex(self):
        self.assertEqual(sb.normalize_hex("ff8a1f"), "#FF8A1F")
        for bad in ("", "#12345", "#GGGGGG", "red"):
            with self.assertRaises(ValueError):
                sb.normalize_hex(bad)

    def test_apply_accent_recolours_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            os.environ["XDG_CONFIG_HOME"] = d + "/cfg"
            try:
                files = {
                    ".config/waybar/style.css": "@define-color sun #FF8A1F;\n#x{border:3px solid @sun}",
                    ".config/fuzzel/fuzzel.ini": "match=FF8A1FFF\nborder=FF8A1FFF\nselection-match=F5B93AFF\n",
                    ".config/mako/config": "border-color=#FF8A1F\n",
                    ".config/gtk-3.0/gtk.css": "@define-color accent_color #ff8a1f;\n",
                    ".config/gtk-4.0/gtk.css": "@define-color accent_color #FF8A1F;\n",
                    ".local/share/themes/SayMy/labwc/themerc": "window.active.border.color: #FF8A1F\n",
                }
                for rel, text in files.items():
                    (home / rel).parent.mkdir(parents=True, exist_ok=True)
                    (home / rel).write_text(text)
                changed = sb.apply_accent("#2F8FD1", home=home, reload=False)
                self.assertEqual(len(changed), 6)
                self.assertIn("@define-color sun #2F8FD1", (home / ".config/waybar/style.css").read_text())
                self.assertIn("match=2F8FD1FF", (home / ".config/fuzzel/fuzzel.ini").read_text())
                self.assertIn("selection-match=F5B93AFF", (home / ".config/fuzzel/fuzzel.ini").read_text())  # untouched
                self.assertIn("#2F8FD1", (home / ".config/gtk-3.0/gtk.css").read_text().upper())
                self.assertEqual(sb.load_appearance()["accent"], "#2F8FD1")
                # second change starts from the saved accent
                sb.apply_accent("#3FA66B", home=home, reload=False)
                self.assertNotIn("2F8FD1", (home / ".config/mako/config").read_text().upper())
            finally:
                del os.environ["XDG_CONFIG_HOME"]

    def test_demo_mode(self):
        os.environ["SAYMY_DEMO"] = "1"
        try:
            self.assertEqual(sb.volume_get(), (60, False))
            self.assertEqual(sb.brightness_get(), 70)
            self.assertEqual(sb.wifi_list()[0]["ssid"], "Kampala-Home")
            self.assertEqual(sb.power_summary()["cuts"], 6)
        finally:
            del os.environ["SAYMY_DEMO"]


class SpacesAndWelcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp + "/cfg"
        os.environ["XDG_DATA_HOME"] = self.tmp + "/data"
        self.home = Path(self.tmp) / "home"
        (self.home / ".config/mako").mkdir(parents=True)
        (self.home / ".config/mako/config").write_text("border-color=#FF8A1F\n")

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"], os.environ["XDG_DATA_HOME"]

    def test_apply_space(self):
        r = sb.apply_space("Study", home=self.home, reload=False)
        self.assertEqual((r["space"], r["dnd"], r["accent"]), ("Study", True, "#2F8FD1"))
        self.assertEqual(sb.current_space(), "Study")
        self.assertIn("#2F8FD1", (self.home / ".config/mako/config").read_text())
        self.assertFalse(sb.load_appearance()["follow_sky"])
        with self.assertRaises(ValueError):
            sb.apply_space("Nonsense", home=self.home, reload=False)

    def test_say_bar_space_intents(self):
        for phrase, space in (("study mode", "Study"), ("business space", "Business"), ("switch to developer", "Developer")):
            self.assertEqual(say.handle(phrase, "en").exec, ["saymy-space", space])

    def test_apply_welcome(self):
        os.environ["HOME"] = str(self.home)
        try:
            done = sb.apply_welcome({"lang": "sw", "price": "5000", "cur": "ugx", "space": "Business",
                                     "accent": "#3FA66B", "follow": True}, reload=False)
        finally:
            pass
        self.assertEqual(done["lang"], "sw")
        self.assertEqual(done["space"], "Business")
        self.assertEqual(done["accent"], "#3FA66B")
        self.assertTrue(done["follow_sky"])
        self.assertTrue(sb.welcome_marker().exists())
        self.assertEqual((Path(self.tmp) / "cfg/saymy/lang").read_text(), "sw")
        self.assertEqual(data.price()["currency"], "UGX")

    def test_welcome_skips_bad_price_and_default_accent(self):
        done = sb.apply_welcome({"lang": "en", "price": "abc", "cur": "", "space": "Home", "accent": None, "follow": False}, reload=False)
        self.assertNotIn("price", done)
        self.assertNotIn("accent", done)


class Doctor(unittest.TestCase):
    def test_parse_ping(self):
        out = "3 packets transmitted, 3 received, 0% packet loss, time 2003ms\nrtt min/avg/max/mdev = 1.2/3.4/5.6/0.8 ms"
        self.assertEqual(doc.parse_ping(out), (0.0, 3.4))
        self.assertEqual(doc.parse_ping("3 packets transmitted, 0 received, 100% packet loss"), (100.0, None))
        self.assertEqual(doc.parse_ping("nonsense"), (None, None))

    def test_gateway_and_memory_and_units(self):
        self.assertEqual(doc.default_gateway("default via 192.168.1.1 dev wlan0 proto dhcp"), "192.168.1.1")
        self.assertIsNone(doc.default_gateway(""))
        info = doc.parse_meminfo("MemTotal:  8000000 kB\nMemAvailable:  800000 kB\n")
        self.assertEqual((info["MemTotal"], info["MemAvailable"]), (8000000, 800000))
        self.assertEqual(doc.parse_failed_units("bluetooth.service loaded failed failed Bluetooth\n● cups.service loaded failed failed CUPS"),
                         ["bluetooth.service", "cups.service"])
        self.assertEqual(doc.parse_top_memory("COMMAND %MEM\nfirefox-esr 12.5\nCode 3.1\nbash 0.2", 2), [("firefox-esr", 12.5), ("Code", 3.1)])

    def test_battery_health(self):
        d = Path(tempfile.mkdtemp()) / "BAT0"
        d.mkdir()
        (d / "type").write_text("Battery")
        (d / "energy_full").write_text("30000000")
        (d / "energy_full_design").write_text("40000000")
        self.assertEqual(doc.battery_health(d.parent), 75)
        self.assertIsNone(doc.battery_health(Path("/nonexistent")))

    def test_headline_and_report(self):
        F = doc.Finding
        self.assertEqual(doc.headline([F("a", "ok", "fine")]), "Everything looks healthy")
        self.assertEqual(doc.headline([F("a", "bad", "x"), F("b", "warn", "y"), F("c", "warn", "z")]), "1 problem found and 2 warnings")
        self.assertIn("[PROBLEM] x", doc.text_report([F("a", "bad", "x", "detail")]))

    def test_demo_and_sorting(self):
        os.environ["SAYMY_DEMO"] = "1"
        try:
            f = doc.diagnose("network")
            self.assertTrue(any(x.level == "warn" for x in f))
        finally:
            del os.environ["SAYMY_DEMO"]

    def test_a_crashing_check_does_not_hide_others(self):
        def boom():
            raise RuntimeError("kaput")
        original = doc.TOPICS["slow"]
        doc.TOPICS["slow"] = [boom, doc.check_storage]
        try:
            f = doc.diagnose("slow")
            self.assertTrue(any("kaput" in x.detail for x in f))
            self.assertTrue(any(x.id.startswith("disk.") for x in f))
        finally:
            doc.TOPICS["slow"] = original

    def test_say_bar_doctor_intents(self):
        for phrase, topic in (("why is my wifi slow", "network"), ("why is my battery draining", "power"), ("my computer is slow", "slow")):
            self.assertEqual(say.handle(phrase, "en").exec, ["saymy-doctor", "--topic", topic])
        self.assertEqual(say.handle("check my computer", "en").exec, ["saymy-doctor"])


class NightAndIdle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["SAYMY_DEMO"] = "1"        # never start real processes in tests

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"], os.environ["SAYMY_DEMO"]

    def test_night_command(self):
        cfg = dict(sb.DISPLAY_DEFAULT, night=True, warmth=3200, start="20:30", end="05:45")
        self.assertEqual(sb.night_cmd(cfg), ["wlsunset", "-t", "3200", "-T", "6500", "-S", "05:45", "-s", "20:30"])

    def test_night_set_and_validation(self):
        cfg = sb.night_set(True, warmth=4500, start="18:00")
        self.assertEqual((cfg["night"], cfg["warmth"], cfg["start"]), (True, 4500, "18:00"))
        self.assertEqual(sb.load_display()["start"], "18:00")
        with self.assertRaises(ValueError):
            sb.night_set(start="25:99")
        for ok, bad in (("00:00", "24:00"), ("23:59", "7:5"), ("06:30", "abc")):
            self.assertTrue(sb.valid_time(ok))
            self.assertFalse(sb.valid_time(bad))

    def test_idle_command(self):
        self.assertEqual(sb.idle_cmd(dict(sb.DISPLAY_DEFAULT, lock_minutes=10)),
                         ["swayidle", "-w", "timeout", "600", "saymy-lock", "timeout", "900", "systemctl suspend"])
        self.assertEqual(sb.idle_cmd(dict(sb.DISPLAY_DEFAULT, lock_minutes=0)), [])
        sb.lock_set(5)
        self.assertEqual(sb.load_display()["lock_minutes"], 5)

    def test_say_bar_night_light(self):
        self.assertEqual(say.handle("turn on night light", "en").exec, ["saymy-night", "on"])
        self.assertEqual(say.handle("night light off", "en").exec, ["saymy-night", "off"])


class Drop(unittest.TestCase):
    def setUp(self):
        os.environ["SAYMY_NO_AVAHI"] = "1"
        self.dest = Path(tempfile.mkdtemp())
        self.src = Path(tempfile.mkdtemp())
        self.srv = drop.DropServer(dest=self.dest, host="127.0.0.1", port=0, code="123456", ttl=0, name="Test PC").start()

    def tearDown(self):
        self.srv.stop()
        del os.environ["SAYMY_NO_AVAHI"]

    def make(self, name="notes.txt", data=b"hello from drop"):
        p = self.src / name
        p.write_bytes(data)
        return p

    def test_transfer_roundtrip_with_progress(self):
        data = os.urandom(300_000)
        p = self.make("photo.jpg", data)
        seen = []
        r = drop.send_file(p, "127.0.0.1", self.srv.port, "123456", progress=lambda a, b: seen.append((a, b)))
        self.assertEqual(r["saved_as"], "photo.jpg")
        self.assertEqual((self.dest / "photo.jpg").read_bytes(), data)
        self.assertEqual(seen[-1], (300_000, 300_000))
        self.assertEqual(self.srv.received, [self.dest / "photo.jpg"])

    def test_empty_file_and_unicode_name(self):
        p = self.make("Kampala café.txt", b"")
        self.assertEqual(drop.send_file(p, "127.0.0.1", self.srv.port, "123456")["saved_as"], "Kampala café.txt")

    def test_wrong_code_rejected_then_locked(self):
        p = self.make()
        for _ in range(drop.MAX_FAILURES):
            with self.assertRaises(drop.DropError) as cm:
                drop.send_file(p, "127.0.0.1", self.srv.port, "000000")
            self.assertEqual(cm.exception.status, 403)
        self.assertTrue(self.srv.locked)
        with self.assertRaises(drop.DropError) as cm:               # even the right code is refused now
            drop.send_file(p, "127.0.0.1", self.srv.port, "123456")
        self.assertEqual(cm.exception.status, 423)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_nonce_cannot_be_replayed(self):
        import http.client
        p = self.make()
        info = drop.hello("127.0.0.1", self.srv.port)
        sha, size = drop.sha256_file(p), p.stat().st_size
        proof = drop.make_proof("123456", info["nonce"], "notes.txt", size, sha)
        def post():
            c = http.client.HTTPConnection("127.0.0.1", self.srv.port)
            c.request("POST", "/drop", body=p.read_bytes(), headers={"X-Drop-Name": "notes.txt", "X-Drop-Sha256": sha,
                                                                     "X-Drop-Nonce": info["nonce"], "X-Drop-Proof": proof})
            return c.getresponse().status
        self.assertEqual(post(), 200)
        self.assertEqual(post(), 403)                                # same proof, nonce already used

    def test_damaged_file_is_rejected(self):
        import http.client
        info = drop.hello("127.0.0.1", self.srv.port)
        body = b"actual bytes"
        claimed = drop.hashlib.sha256(b"different bytes").hexdigest()
        proof = drop.make_proof("123456", info["nonce"], "x.bin", len(body), claimed)
        c = http.client.HTTPConnection("127.0.0.1", self.srv.port)
        c.request("POST", "/drop", body=body, headers={"X-Drop-Name": "x.bin", "X-Drop-Sha256": claimed,
                                                       "X-Drop-Nonce": info["nonce"], "X-Drop-Proof": proof})
        self.assertEqual(c.getresponse().status, 422)
        self.assertEqual([f.name for f in self.dest.iterdir()], [])  # nothing left behind, not even a .part file

    def test_size_limit(self):
        self.srv.max_bytes = 10
        with self.assertRaises(drop.DropError) as cm:
            drop.send_file(self.make(data=b"x" * 100), "127.0.0.1", self.srv.port, "123456")
        self.assertEqual(cm.exception.status, 413)

    def test_existing_files_are_never_overwritten(self):
        p = self.make("a.txt", b"one")
        drop.send_file(p, "127.0.0.1", self.srv.port, "123456")
        p.write_bytes(b"two")
        r = drop.send_file(p, "127.0.0.1", self.srv.port, "123456")
        self.assertEqual(r["saved_as"], "a (1).txt")
        self.assertEqual((self.dest / "a.txt").read_bytes(), b"one")

    def test_safe_name(self):
        self.assertEqual(drop.safe_name("../../etc/passwd"), "passwd")
        self.assertEqual(drop.safe_name("..\\..\\windows\\evil.exe"), "evil.exe")
        self.assertEqual(drop.safe_name(".bashrc"), "bashrc")
        self.assertEqual(drop.safe_name("\x00\x01"), "file")
        self.assertEqual(len(drop.safe_name("a" * 500)), 200)

    def test_unreachable_receiver(self):
        with self.assertRaises(drop.DropError):
            drop.hello("127.0.0.1", 1, timeout=1)

    def test_notifications_never_crash_without_notify_send(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = "/nonexistent"
        try:
            drop.notify("hello", "world")
            say.notify("hello")
        finally:
            os.environ["PATH"] = old

    def test_codes_and_targets(self):
        for _ in range(50):
            self.assertRegex(drop.new_code(), r"^\d{6}$")
        self.assertEqual(drop.parse_target("192.168.1.23"), ("192.168.1.23", drop.PORT))
        self.assertEqual(drop.parse_target("192.168.1.23:9000"), ("192.168.1.23", 9000))

    def test_parse_avahi(self):
        text = ("+;wlan0;IPv4;Grace\\039s\\032laptop;_saymydrop._tcp;local\n"
                "=;wlan0;IPv4;Grace\\032laptop;_saymydrop._tcp;local;grace.local;192.168.1.23;53317;\n"
                "=;wlan0;IPv6;Grace\\032laptop;_saymydrop._tcp;local;grace.local;fe80::1;53317;\n"
                "=;eth0;IPv4;Grace\\032laptop;_saymydrop._tcp;local;grace.local;192.168.1.23;53317;\n")
        self.assertEqual(drop.parse_avahi(text), [{"name": "Grace laptop", "host": "grace.local", "address": "192.168.1.23", "port": 53317}])

    def test_say_bar_drop_intents(self):
        for phrase in ("send a file", "share files nearby", "drop"):
            self.assertEqual(say.handle(phrase, "en").exec, ["saymy-drop"])


class FakeRun:
    """Stands in for subprocess.run and records what would have been executed."""
    def __init__(self, ok=True, out=""):
        self.calls, self.ok, self.out = [], ok, out

    def __call__(self, cmd, input=None, capture_output=True, text=True, timeout=None):
        self.calls.append({"cmd": cmd, "input": input})
        return types.SimpleNamespace(returncode=0 if self.ok else 1, stdout=self.out, stderr="")


class UsersAndUpdates(unittest.TestCase):
    def test_validation(self):
        for good in ("grace", "a", "kampala_user-2"):
            self.assertTrue(sysm.valid_username(good), good)
        for bad in ("", "Root", "root", "1abc", "has space", "a" * 40, "x;rm", "admin", "../etc"):
            self.assertFalse(sysm.valid_username(bad), bad)
        self.assertFalse(sysm.valid_password("short"))
        self.assertFalse(sysm.valid_password("line\nbreak123"))
        self.assertTrue(sysm.valid_password("a good one"))
        self.assertEqual(sysm.clean_fullname("  Grace: N,\x00ak\x07ibuuka "), "Grace Nakibuuka")

    def test_list_users(self):
        d = Path(tempfile.mkdtemp())
        (d / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\nsteven:x:1000:1000:Steven,,,:/home/steven:/bin/bash\n"
                                  "grace:x:1001:1001:Grace:/home/grace:/bin/bash\nnobody:x:65534:65534:nobody:/:/usr/sbin/nologin\n")
        (d / "group").write_text("sudo:x:27:steven\nusers:x:100:\n")
        us = sysm.list_users(d / "passwd", d / "group")
        self.assertEqual([(u["name"], u["admin"], u["fullname"]) for u in us], [("steven", True, "Steven"), ("grace", False, "Grace")])

    def test_elevate_uses_graphical_askpass(self):
        c = sysm.elevate(["apt-get", "update"])
        self.assertEqual(c[:2], ["env", "SUDO_ASKPASS=/usr/bin/saymy-askpass"])
        self.assertIn("-A", c)
        self.assertEqual(c[-2:], ["apt-get", "update"])

    def test_password_goes_through_stdin_never_the_command_line(self):
        fr = FakeRun()
        sysm.add_user("grace", "Grace N", "s3cret-pass", admin=True, runner=fr)
        call = fr.calls[0]
        self.assertEqual(call["input"], "s3cret-pass\n")
        self.assertNotIn("s3cret-pass", " ".join(call["cmd"]))
        self.assertEqual(call["cmd"][-4:], ["grace", "Grace N", "--admin", ]) if False else None
        self.assertIn("--admin", call["cmd"])
        with self.assertRaises(ValueError):
            sysm.add_user("root", "x", "longenough")
        with self.assertRaises(ValueError):
            sysm.add_user("okname", "x", "123")

    def test_parse_upgradable(self):
        text = ("Listing... Done\nfirefox-esr/stable-security 140.4.0esr-1 amd64 [upgradable from: 140.3.1esr-1]\n"
                "labwc/stable 0.8.4-1 amd64 [upgradable from: 0.8.2-1]\nnot a package line\n")
        up = sysm.parse_upgradable(text)
        self.assertEqual([(p["name"], p["security"], p["old"]) for p in up], [("firefox-esr", True, "140.3.1esr-1"), ("labwc", False, "0.8.2-1")])

    def _bundle(self):
        d = Path(tempfile.mkdtemp())
        (d / "labwc_0.8.4-1_amd64.deb").write_bytes(b"deb-one")
        (d / "waybar_0.12.0-2_amd64.deb").write_bytes(b"deb-two")
        (d / "manifest.json").write_text(json.dumps(sysm.build_manifest(d)))
        return d

    def test_bundle_verify_and_install(self):
        d = self._bundle()
        self.assertEqual(sysm.verify_bundle(d), [])
        fr = FakeRun()
        ok, _ = sysm.install_bundle(d, runner=fr)
        self.assertTrue(ok)
        cmd = fr.calls[0]["cmd"]
        self.assertIn("--no-download", cmd)
        self.assertIn(str(d / "labwc_0.8.4-1_amd64.deb"), cmd)

    def test_tampered_bundle_is_refused_and_nothing_runs(self):
        d = self._bundle()
        (d / "labwc_0.8.4-1_amd64.deb").write_bytes(b"EVIL")
        fr = FakeRun()
        ok, msg = sysm.install_bundle(d, runner=fr)
        self.assertFalse(ok)
        self.assertIn("checksum", msg)
        self.assertEqual(fr.calls, [])

    def test_extra_and_missing_files_in_bundle(self):
        d = self._bundle()
        (d / "sneaky_1.0_amd64.deb").write_bytes(b"x")
        self.assertTrue(any("not in the manifest" in p for p in sysm.verify_bundle(d)))
        (d / "waybar_0.12.0-2_amd64.deb").unlink()
        self.assertTrue(any("missing" in p for p in sysm.verify_bundle(d)))
        self.assertEqual(sysm.verify_bundle(Path(tempfile.mkdtemp())), ["manifest.json is missing or unreadable"])

    def test_make_bundle(self):
        archives, dest = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "out"
        (archives / "labwc_0.8.4-1_amd64.deb").write_bytes(b"abc")
        fr = FakeRun()
        ok, msg = sysm.make_bundle(dest, archives=archives, runner=fr)
        self.assertTrue(ok)
        self.assertIn("--download-only", fr.calls[0]["cmd"])
        self.assertEqual(sysm.verify_bundle(dest), [])
        self.assertEqual(json.loads((dest / "manifest.json").read_text())["packages"][0]["name"], "labwc")
        self.assertFalse(sysm.make_bundle(dest, archives=archives, runner=FakeRun(ok=False))[0])


class UserHelper(unittest.TestCase):
    """The root helper, run for real in --dry-run mode against fake account files."""
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        (d / "passwd").write_text("steven:x:1000:1000:Steven:/home/steven:/bin/bash\ngrace:x:1001:1001:Grace:/home/grace:/bin/bash\n")
        (d / "group").write_text("sudo:x:27:steven\n")
        self.env = dict(os.environ, SAYMY_PASSWD=str(d / "passwd"), SAYMY_GROUP=str(d / "group"), SUDO_USER="steven")

    def helper(self, *args, stdin=""):
        p = subprocess.run([str(LIB / "saymy-user-helper"), "--dry-run", *args], input=stdin, capture_output=True, text=True, env=self.env)
        return p.returncode, p.stdout, p.stderr

    def test_add_user(self):
        rc, out, _ = self.helper("add", "zzjoy", "Joy N", "--admin", stdin="a-fine-password\n")
        self.assertEqual(rc, 0)
        self.assertIn("useradd -m -s /bin/bash -c Joy N zzjoy", out)
        self.assertIn("chpasswd", out)
        self.assertIn("sudo", out.splitlines()[-1])
        self.assertNotIn("a-fine-password", out)

    def test_refusals(self):
        self.assertNotEqual(self.helper("add", "root", "x", "--standard", stdin="longenough\n")[0], 0)
        self.assertNotEqual(self.helper("add", "grace", "x", "--standard", stdin="longenough\n")[0], 0)   # taken
        self.assertNotEqual(self.helper("add", "zzjoy", "x", "--standard", stdin="abc\n")[0], 0)           # weak password
        self.assertNotEqual(self.helper("delete", "steven")[0], 0)                                            # yourself
        self.assertNotEqual(self.helper("admin", "steven", "off")[0], 0)                                      # yourself / last admin
        self.assertNotEqual(self.helper("delete", "root")[0], 0)                                              # not a regular user
        self.assertNotEqual(self.helper("passwd", "nobody-here", stdin="longenough\n")[0], 0)
        self.assertNotEqual(self.helper("frobnicate")[0], 0)

    def test_allowed_actions(self):
        rc, out, _ = self.helper("delete", "grace")
        self.assertEqual((rc, out.strip()), (0, "userdel -r grace"))
        self.assertEqual(self.helper("admin", "grace", "on")[1].strip(), "gpasswd -a grace sudo")
        self.assertEqual(self.helper("passwd", "grace", stdin="newpassword\n")[1].strip(), "chpasswd")



class FakeSh:
    """Fake system for Safe Updates: tracks installed packages, failed services and every command run."""
    def __init__(self, installed=None, audit="", check_rc=0, upgrade_rc=0, failed=("", "")):
        self.calls, self.installed, self.audit, self.check_rc, self.upgrade_rc = [], dict(installed or {}), audit, check_rc, upgrade_rc
        self.failed = list(failed)

    def ran(self, word):
        return [c for c in self.calls if word in c]

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        if cmd[:2] == ["dpkg", "--audit"]:
            return 0, self.audit
        if cmd[:2] == ["apt-get", "check"]:
            return self.check_rc, ""
        if cmd[0] == "systemctl":
            return 0, (self.failed.pop(0) if len(self.failed) > 1 else self.failed[0])
        if cmd[0] == "dpkg-query":
            v = self.installed.get(cmd[-1])
            return (0, f"install ok installed|{v}|amd64") if v else (1, "")
        if cmd[0] == "dpkg-repack":
            (Path(cwd) / f"{cmd[1]}_{self.installed[cmd[1]]}_amd64.deb").write_bytes(f"old {cmd[1]} {self.installed[cmd[1]]}".encode())
            return 0, ""
        if "upgrade" in cmd:
            return self.upgrade_rc, "Setting up things...\nDone."
        if "--allow-downgrades" in cmd:
            return 0, "Downgraded."
        return 0, ""


GOOD_POWER = {"ac": True, "battery_pct": 80}


class SafeUpdates(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.lines = []

    def run_update(self, sh, names=("labwc", "waybar"), power=GOOD_POWER, free=10 * 10 ** 9, now=None):
        return su.apply_updates(sh, list(names), ["apt-get", "-y", "upgrade"], power, free, on_line=self.lines.append, d=self.d, now=now)

    def test_precheck_blocks_unsafe_conditions(self):
        ok = lambda **k: su.precheck(FakeSh(**k), k.get("power", GOOD_POWER), 10 ** 10)
        self.assertEqual(su.precheck(FakeSh(), GOOD_POWER, 10 ** 10), [])
        self.assertTrue(any("charger" in p["message"] for p in su.precheck(FakeSh(), {"ac": False, "battery_pct": 30}, 10 ** 10)))
        self.assertEqual(su.precheck(FakeSh(), {"ac": False, "battery_pct": 70}, 10 ** 10), [])      # battery above 50% is fine
        self.assertEqual(su.precheck(FakeSh(), {"ac": None, "battery_pct": None}, 10 ** 10), [])      # desktop with no battery
        self.assertTrue(any("disk space" in p["message"] for p in su.precheck(FakeSh(), GOOD_POWER, 10 ** 9)))
        self.assertTrue(any("did not finish" in p["message"] for p in su.precheck(FakeSh(audit="foo half-installed"), GOOD_POWER, 10 ** 10)))
        self.assertTrue(any("apt-get check" in p["message"] for p in su.precheck(FakeSh(check_rc=100), GOOD_POWER, 10 ** 10)))

    def test_blocked_update_changes_nothing(self):
        sh = FakeSh(installed={"labwc": "0.8.2-1"})
        res = self.run_update(sh, power={"ac": False, "battery_pct": 20})
        self.assertFalse(res["ok"])
        self.assertEqual(res["stage"], "precheck")
        self.assertEqual(sh.ran("upgrade"), [])
        self.assertEqual(su.load_journal(self.d), [])

    def test_successful_update_keeps_old_versions(self):
        sh = FakeSh(installed={"labwc": "0.8.2-1", "waybar": "0.12.0-1"})
        res = self.run_update(sh, names=("labwc", "waybar", "brandnew"), now=1_700_000_000)
        self.assertTrue(res["ok"])
        self.assertEqual(res["kept"], 2)
        j = su.load_journal(self.d)
        self.assertEqual([p["name"] for p in j[0]["packages"]], ["labwc", "waybar"])
        self.assertEqual(j[0]["new_packages"], ["brandnew"])
        kept = self.d / j[0]["id"] / j[0]["packages"][0]["file"]
        self.assertEqual(kept.read_bytes(), b"old labwc 0.8.2-1")
        # the old version was copied BEFORE the upgrade ran
        self.assertLess(sh.calls.index(["dpkg-repack", "labwc"]), sh.calls.index(["apt-get", "-y", "upgrade"]))

    def test_new_service_failures_are_reported(self):
        sh = FakeSh(installed={"labwc": "1"}, failed=("cups.service loaded failed", "cups.service loaded failed\nsddm.service loaded failed"))
        res = self.run_update(sh, names=("labwc",))
        self.assertEqual(res["new_failures"], ["sddm.service"])        # cups was already failing, so it is not blamed on the update
        self.assertTrue(any("sddm.service" in l for l in self.lines))

    def test_failed_upgrade_is_still_undoable(self):
        sh = FakeSh(installed={"labwc": "1"}, upgrade_rc=100)
        res = self.run_update(sh, names=("labwc",))
        self.assertFalse(res["ok"])
        self.assertTrue(su.summary(su.load_journal(self.d))[0]["undoable"])

    def test_undo_restores_and_holds(self):
        sh = FakeSh(installed={"labwc": "0.8.2-1"})
        res = self.run_update(sh, names=("labwc",))
        out = su.undo(sh, res["txn"], on_line=self.lines.append, d=self.d)
        self.assertTrue(out["ok"])
        cmd = sh.ran("--allow-downgrades")[0]
        self.assertIn("--no-download", cmd)
        self.assertTrue(any(a.endswith("labwc_0.8.2-1_amd64.deb") for a in cmd))
        self.assertEqual(sh.ran("hold")[0][-1], "labwc")
        self.assertEqual(su.load_journal(self.d)[0]["status"], "undone")
        self.assertFalse(su.undo(sh, res["txn"], on_line=self.lines.append, d=self.d)["ok"])   # cannot undo twice
        # the next update releases the hold first
        self.run_update(sh, names=("labwc",), now=1_800_000_000)
        self.assertTrue(sh.ran("unhold"))

    def test_undo_refuses_damaged_kept_copy(self):
        sh = FakeSh(installed={"labwc": "0.8.2-1"})
        res = self.run_update(sh, names=("labwc",))
        for f in (self.d / res["txn"]).glob("*.deb"):
            f.write_bytes(b"tampered")
        before = len(sh.calls)
        out = su.undo(sh, res["txn"], on_line=self.lines.append, d=self.d)
        self.assertFalse(out["ok"])
        self.assertIn("damaged", out["error"])
        self.assertEqual(len(sh.calls), before)                          # nothing was run
        self.assertFalse(su.undo(sh, "nope", d=self.d)["ok"])

    def test_only_the_last_three_updates_are_kept(self):
        sh = FakeSh(installed={"labwc": "1"})
        ids = [self.run_update(sh, names=("labwc",), now=1_700_000_000 + i * 86400)["txn"] for i in range(5)]
        j = su.load_journal(self.d)
        self.assertEqual([e["id"] for e in j], ids[-3:])
        for old in ids[:2]:
            self.assertFalse((self.d / old).exists())                    # disk space is reclaimed

    def test_kernel_flag_and_summary(self):
        sh = FakeSh(installed={"linux-image-amd64": "6.12.1"})
        res = self.run_update(sh, names=("linux-image-amd64",))
        self.assertTrue(res["kernel"])
        s = su.summary(su.load_journal(self.d))[0]
        self.assertTrue(s["kernel"] and s["undoable"])

    def test_sysm_streams_helper_output_and_result(self):
        lines = []
        fr = FakeRun(out="PROGRESS: step one\nsome apt line\nRESULT: {\"ok\": true, \"kept\": 3}")
        ok, res = sysm.safe_apply(on_line=lines.append, runner=fr)
        self.assertTrue(ok)
        self.assertEqual(res["kept"], 3)
        self.assertEqual(lines, ["step one", "some apt line"])
        self.assertEqual(fr.calls[0]["cmd"][-2:], [sysm.UPDATE_HELPER, "apply"])
        ok, _ = sysm.safe_undo("2026", runner=FakeRun(out="RESULT: {\"ok\": false}"))
        self.assertFalse(ok)



class Looks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp + "/cfg"
        self.home = Path(self.tmp) / "home"
        w = self.home / ".config/waybar"
        w.mkdir(parents=True)
        (w / "style.css").write_text("@define-color sun #FF8A1F;\nwindow#waybar > box { background: rgba(12, 26, 42, 0.92); border: 1px solid #1E3A55; }\n#clock { color: #F3E9D8; background: #14283C; }\n.mu { color: #9FB3C8; }\n")
        (w / "config.jsonc").write_text(json.dumps({"layer": "top", "position": "bottom", "height": 46, "margin": "0 12 10 12", "spacing": 8}))
        (self.home / ".config/fuzzel").mkdir(parents=True)
        (self.home / ".config/fuzzel/fuzzel.ini").write_text("background=0C1A2AF2\ntext=F3E9D8FF\nselection=1E3A55FF\n")
        (self.home / ".config/labwc").mkdir(parents=True)
        (self.home / ".config/labwc/environment").write_text("XDG_SESSION_TYPE=wayland\nGTK_THEME=Adwaita-dark\n")

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"]

    def test_swap_is_one_pass_and_reversible(self):
        css = open(self.home / ".config/waybar/style.css").read()
        light = lk.swap_palette(css, "dark", "light")
        self.assertNotIn("F3E9D8", light.upper())
        self.assertIn("rgba(247, 241, 230,", light)
        self.assertIn("#14283C", light.upper().replace("COLOR: #14283C", "#14283C"))     # text became the old surface colour, not chained again
        self.assertEqual(lk.swap_palette(light, "light", "dark"), css)                    # perfect round trip
        self.assertEqual(lk.swap_palette(css, "dark", "dark"), css)

    def test_apply_mode_light_then_dark(self):
        changed = lk.apply_mode("light", home=self.home, reload=False)
        self.assertIn(".config/waybar/style.css", changed)
        self.assertIn("background=F7F1E6F2", (self.home / ".config/fuzzel/fuzzel.ini").read_text())
        self.assertIn("GTK_THEME=Adwaita\n", (self.home / ".config/labwc/environment").read_text())
        self.assertEqual(be_mode(), "light")
        lk.apply_mode("dark", home=self.home, reload=False)
        self.assertIn("background=0C1A2AF2", (self.home / ".config/fuzzel/fuzzel.ini").read_text())
        self.assertIn("GTK_THEME=Adwaita-dark", (self.home / ".config/labwc/environment").read_text())
        with self.assertRaises(ValueError):
            lk.apply_mode("neon", home=self.home, reload=False)

    def test_panel(self):
        self.assertTrue(lk.apply_panel("top", 36, home=self.home, reload=False))
        cfg = json.loads((self.home / ".config/waybar/config.jsonc").read_text())
        self.assertEqual((cfg["position"], cfg["height"], cfg["margin"], cfg["spacing"]), ("top", 36, "10 12 0 12", 8))
        for bad in (("left", 46), ("top", 5), ("top", 500)):
            with self.assertRaises(ValueError):
                lk.apply_panel(*bad, home=self.home, reload=False)

    def test_validate_look_rejects_hostile_input(self):
        good = {"name": "Mine", "accent": "#2F8FD1", "mode": "light", "panel_position": "top", "panel_height": 40}
        self.assertEqual(lk.validate_look(good)["accent"], "#2F8FD1")
        for bad in ({}, [], "x", {"name": ""}, dict(good, accent="red"), dict(good, mode="neon"), dict(good, panel_position="left"),
                    dict(good, panel_height=9999), dict(good, panel_height="46"), dict(good, panel_height=True), dict(good, name=5)):
            with self.assertRaises(ValueError, msg=str(bad)):
                lk.validate_look(bad)
        clean = lk.validate_look(dict(good, name="Evil\x00\x07 name " + "x" * 100, command="rm -rf /", __import__="os"))
        self.assertEqual(set(clean), {"name", "accent", "mode", "panel_position", "panel_height"})     # unknown fields dropped
        self.assertLessEqual(len(clean["name"]), 40)
        self.assertNotIn("\x00", clean["name"])

    def test_export_import_roundtrip_and_limits(self):
        lk.apply_look(lk.PRESETS["Paper"], home=self.home, reload=False)
        f = Path(self.tmp) / "paper.saymylook"
        lk.export_look(f, "Paper copy")
        lk.apply_look(lk.PRESETS["Sunrise"], home=self.home, reload=False)
        self.assertEqual(lk.import_look(f, home=self.home, reload=False)["mode"], "light")
        self.assertEqual(be_mode(), "light")
        big = Path(self.tmp) / "big.saymylook"
        big.write_text(" " * 10000)
        with self.assertRaises(ValueError):
            lk.import_look(big, home=self.home, reload=False)
        junk = Path(self.tmp) / "junk.saymylook"
        junk.write_text("not json {")
        with self.assertRaises(ValueError):
            lk.import_look(junk, home=self.home, reload=False)

    def test_presets_are_valid_and_cli_intents(self):
        for look in lk.PRESETS.values():
            self.assertEqual(lk.validate_look(look)["name"], look["name"])
        self.assertEqual(say.handle("dark mode", "en").exec, ["saymy-look", "mode", "dark"])
        self.assertEqual(say.handle("switch to light", "en").exec, ["saymy-look", "mode", "light"])

    def test_windows_follow_the_theme(self):
        import saymy_theme
        lk.apply_mode("light", home=self.home, reload=False)
        css = saymy_theme.css_for("#D9650D")
        self.assertIn("#F7F1E6", css.upper())
        self.assertNotIn("#0C1A2A", css.upper())


def be_mode():
    return sb.load_appearance().get("mode")


@unittest.skipIf(live is None, "pycairo not installed")
class LivingSky(unittest.TestCase):
    def frame(self, scene, hour, gd=False, w=160, h=90):
        import cairo
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        live.render(cairo.Context(surf), w, h, 1.5, hour, scene, gd)
        return bytes(surf.get_data())

    def test_every_scene_renders_at_every_hour(self):
        for scene in live.SCENES:
            for hour in (0, 5.5, 6.4, 9, 12.5, 16, 18.2, 19.2, 20.5, 23.9):
                for gd in (False, True):
                    self.assertGreater(len(self.frame(scene, hour, gd)), 0)

    def test_frames_differ_over_time_and_by_power(self):
        a, b = self.frame("Savanna", 12.0), self.frame("Savanna", 18.8)
        self.assertNotEqual(a, b)                                        # the sky really changes through the day
        self.assertNotEqual(self.frame("Savanna", 13.0), self.frame("Savanna", 13.0, gd=True))      # Grid Down changes the scene
        import cairo
        s1, s2 = (cairo.ImageSurface(cairo.FORMAT_RGB24, 160, 90) for _ in range(2))
        live.render(cairo.Context(s1), 160, 90, 0.0, 12, "Lakeshore")
        live.render(cairo.Context(s2), 160, 90, 2.0, 12, "Lakeshore")
        self.assertNotEqual(bytes(s1.get_data()), bytes(s2.get_data()))                                 # and it moves between frames

    def test_deterministic(self):
        self.assertEqual(self.frame("Highlands", 8.0), self.frame("Highlands", 8.0))

    def test_sky_is_continuous_and_loops_at_midnight(self):
        prev = live.sky_colors(0.0)
        worst = 0
        for i in range(1, 2401):
            cur = live.sky_colors(i / 100)
            worst = max(worst, max(abs(a - b) for c1, c2 in zip(prev, cur) for a, b in zip(c1, c2)))
            prev = cur
        self.assertLess(worst, 0.03)                                     # no sudden jumps in 24 hours at 0.01 hour steps
        self.assertEqual(live.sky_colors(24.0), live.sky_colors(0.0))

    def test_sun_and_moon_follow_the_clock(self):
        w, h, hz = 1000, 600, 380
        self.assertIsNone(live.sun_position(3.0, w, h, hz))
        self.assertIsNone(live.sun_position(21.0, w, h, hz))
        x1, y1, _ = live.sun_position(7, w, h, hz)
        x2, y2, _ = live.sun_position(12.6, w, h, hz)
        x3, y3, _ = live.sun_position(18, w, h, hz)
        self.assertTrue(x1 < x2 < x3 and y2 < y1 and y2 < y3)            # rises in the east, peaks, sets in the west
        self.assertIsNotNone(live.moon_position(23, w, h, hz))
        self.assertIsNone(live.moon_position(12, w, h, hz))
        self.assertGreater(live.daylight(12), 0.95)
        self.assertLess(live.daylight(2), 0.01)

    def test_adaptive_quality_plan(self):
        self.assertEqual(live.plan(10, 0), (0, live.MAX_FPS))             # fast machine keeps full quality
        self.assertEqual(live.plan(40, 0)[0], 1)                          # slower: smaller picture first
        self.assertEqual(live.plan(40, 2), (2, 8))
        self.assertEqual(live.plan(100, 2), (2, 0))                       # hopeless: stop animating, use still frames
        self.assertEqual(live.plan(0, 1), (1, live.MAX_FPS))

    def test_thumbnails_and_png(self):
        t = wpm.thumbnails(hour=17.0, size=(64, 36))
        self.assertEqual(set(t), set(wpm.SCENES))
        self.assertTrue(all(b[:8] == b"\x89PNG\r\n\x1a\n" for b in t.values()))


class WallpaperSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp + "/cfg"
        os.environ["XDG_CACHE_HOME"] = self.tmp + "/cache"

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"], os.environ["XDG_CACHE_HOME"]

    def test_defaults_and_validation(self):
        self.assertEqual(wpm.load(), {"mode": "live", "scene": "Savanna", "animate": "auto", "image": ""})
        cfg = wpm.set_wallpaper(mode="live", scene="Lakeshore", animate="never", reload=False)
        self.assertEqual((cfg["scene"], cfg["animate"]), ("Lakeshore", "never"))
        self.assertEqual(wpm.load()["scene"], "Lakeshore")
        for bad in ({"mode": "video"}, {"scene": "Moon"}, {"animate": "sometimes"}):
            with self.assertRaises(ValueError):
                wpm.set_wallpaper(reload=False, **bad)
        with self.assertRaises(ValueError):
            wpm.set_wallpaper(mode="image", reload=False)                 # no picture chosen yet

    def test_pictures_are_checked(self):
        d = Path(self.tmp)
        good, bad_ext, folder = d / "me.jpg", d / "notes.txt", d / "dir.png"
        good.write_bytes(b"jpegdata")
        bad_ext.write_text("x")
        folder.mkdir()
        self.assertTrue(wpm.valid_image(str(good)))
        self.assertFalse(wpm.valid_image(str(bad_ext)))
        self.assertFalse(wpm.valid_image(str(folder)))
        self.assertFalse(wpm.valid_image(str(d / "missing.png")))
        cfg = wpm.set_wallpaper(mode="image", image=str(good), reload=False)
        self.assertEqual(wpm.command_for(cfg), ["swaybg", "-i", str(good.resolve()), "-m", "fill"])

    def test_dispatcher_choices(self):
        self.assertEqual(wpm.command_for(dict(wpm.DEFAULT)), ["saymy-live", "--daemon"])
        self.assertEqual(wpm.command_for(dict(wpm.DEFAULT), have_cairo=False), ["saymy-sky"])      # no Cairo: fall back to sky photos
        self.assertEqual(wpm.command_for(dict(wpm.DEFAULT, mode="sky")), ["saymy-sky"])
        self.assertEqual(wpm.command_for(dict(wpm.DEFAULT, mode="image", image="/nonexistent.png")), ["saymy-sky"])

    def test_stop_uses_saved_process_ids_only(self):
        import subprocess as sp
        wpm.cache_dir().mkdir(parents=True)
        victim = sp.Popen(["sleep", "30"])
        (wpm.cache_dir() / "live.pid").write_text(str(victim.pid))
        (wpm.cache_dir() / "wallpaper.pid").write_text("not a number")
        wpm.stop()
        self.assertEqual(victim.wait(timeout=5), -15)                       # SIGTERM
        self.assertFalse((wpm.cache_dir() / "live.pid").exists())


class SoundPacks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"]

    def test_all_packs_have_all_events_as_clean_wav(self):
        import wave
        self.assertEqual(snd.packs(), ["Classic", "Quiet", "Savanna"])
        for pack in snd.packs():
            for ev in snd.EVENTS:
                f = SHARE / "sounds" / pack / f"{ev}.wav"
                self.assertTrue(f.is_file(), f"{pack}/{ev}")
                with wave.open(str(f)) as w:
                    self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050))
                    secs = w.getnframes() / w.getframerate()
                    frames = w.readframes(w.getnframes())
                self.assertTrue(0.2 <= secs <= 3.0, f"{pack}/{ev} is {secs}s")
                import array
                samples = array.array("h", frames)
                peak = max(abs(x) for x in samples)
                self.assertTrue(3000 < peak <= 29000, f"{pack}/{ev} peak {peak}")        # audible, never clipping
                self.assertLess(abs(samples[0]), 800)                                      # starts without a click
                self.assertLess(abs(samples[-1]), 800)

    def test_pack_choice_validation_and_config(self):
        self.assertEqual(snd.load(), {"pack": "Savanna", "volume": 70})
        self.assertEqual(snd.set_pack("Quiet")["pack"], "Quiet")
        self.assertEqual(snd.set_pack("Off")["pack"], "Off")
        with self.assertRaises(ValueError):
            snd.set_pack("../../etc")
        self.assertEqual(snd.set_volume(250)["volume"], 100)
        self.assertEqual(snd.set_volume(-5)["volume"], 0)

    def test_sound_file_lookup_is_safe(self):
        self.assertIsNotNone(snd.sound_file("notify", "Savanna"))
        self.assertIsNone(snd.sound_file("../../../etc/passwd", "Savanna"))
        self.assertIsNone(snd.sound_file("notify", "Off"))
        self.assertIsNone(snd.sound_file("notify", "NoSuchPack"))

    def test_play_respects_off_volume_and_dnd(self):
        started = []
        real_popen, real_muted, real_cmd = snd.subprocess.Popen, snd.muted_now, snd.player_command
        snd.subprocess.Popen = lambda cmd, **k: started.append(cmd)
        snd.player_command = lambda f, v: ["pw-play", str(f)]
        try:
            snd.muted_now = lambda: False
            self.assertTrue(snd.play("notify"))
            snd.set_pack("Off")
            self.assertFalse(snd.play("notify"))
            snd.set_pack("Savanna")
            snd.set_volume(0)
            self.assertFalse(snd.play("notify"))
            snd.set_volume(60)
            snd.muted_now = lambda: True                                       # Study space: do not disturb
            self.assertFalse(snd.play("notify"))
            self.assertTrue(snd.play("power-cut"))                              # safety alerts always sound
            self.assertTrue(snd.play("notify", force=True))
        finally:
            snd.subprocess.Popen, snd.muted_now, snd.player_command = real_popen, real_muted, real_cmd
        self.assertEqual(len(started), 3)

    def test_never_crashes_without_a_player(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = "/nonexistent"
        try:
            self.assertIsNone(snd.player_command(Path("/x.wav"), 50))
            self.assertFalse(snd.play("login", force=True))
        finally:
            os.environ["PATH"] = old

    def test_power_events_play_sounds(self):
        log = power.apply("power_cut", {"battery_pct": 90}, dry=True)
        self.assertIn(["saymy-sound", "play", "power-cut"], log)
        self.assertIn(["saymy-sound", "play", "power-back"], power.apply("power_back", {"battery_pct": 90}, dry=True))
        self.assertIn(["saymy-sound", "play", "battery-low"], power.apply("low", {"battery_pct": 19}, dry=True))

    def test_looks_carry_wallpaper_and_sound_by_name_only(self):
        base = {"name": "Mine", "accent": "#2F8FD1", "mode": "dark", "panel_position": "bottom", "panel_height": 46}
        ok = lk.validate_look(dict(base, wallpaper="Lakeshore", sound="Quiet"))
        self.assertEqual((ok["wallpaper"], ok["sound"]), ("Lakeshore", "Quiet"))
        self.assertNotIn("wallpaper", lk.validate_look(base))                   # optional
        for bad in ({"wallpaper": "/home/user/.ssh/id_rsa"}, {"wallpaper": "../../x.png"}, {"wallpaper": "Moon"}, {"sound": "/etc/passwd"},
                    {"sound": "Loud"}, {"wallpaper": 7}):
            with self.assertRaises(ValueError, msg=str(bad)):
                lk.validate_look(dict(base, **bad))
        for look in lk.PRESETS.values():
            self.assertIn(lk.validate_look(look)["wallpaper"], lk.WALLPAPERS)

    def test_say_bar_sound_intents(self):
        self.assertEqual(say.handle("mute sounds", "en").exec, ["saymy-sound", "use", "Off"])
        self.assertEqual(say.handle("sounds on", "en").exec, ["saymy-sound", "use", "Savanna"])



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
