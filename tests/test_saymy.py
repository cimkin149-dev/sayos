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
import saymy_settings_backend as sb  # noqa: E402
import saymy_doctor as doc  # noqa: E402
import saymy_drop as drop  # noqa: E402


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
