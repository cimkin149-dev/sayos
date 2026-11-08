"""SayMy Drop: send files to a nearby computer with no internet.

How it works
  Receiver  turns Drop on and gets a 6 digit pairing code, shown on its screen. Drop switches itself off after
            10 minutes. The receiver advertises itself on the local network (Avahi) and listens on one port.
  Sender    finds nearby receivers (or types an address), enters the code, picks a file.
  Proof     the code itself never crosses the network. The receiver hands out a one-time random nonce, and the
            sender proves it knows the code by returning HMAC-SHA256(code, nonce|name|size|sha256).
            Five wrong proofs lock the receiver. Each nonce works once and expires in 60 seconds.
  Safety    file names are sanitised (no folders, no hidden files), existing files are never overwritten,
            size is capped, and the SHA-256 is verified before a file is kept.

Honest limits (v0.1): files are not encrypted in transit, so do not send secrets over public Wi-Fi.
Encrypted transfer (pairing-based TLS) is planned.
"""
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import saymy_settings_backend as be

PORT = 53317
SERVICE = "_saymydrop._tcp"
MAX_BYTES = 2 * 1024 ** 3
MAX_FAILURES = 5
NONCE_SECONDS = 60
CHUNK = 64 * 1024


class DropError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ names and proofs
def safe_name(name: str) -> str:
    """A file name that cannot escape the folder or hide itself."""
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().lstrip(".")
    return name[:200] or "file"


def unique_path(folder: Path, name: str) -> Path:
    p = folder / safe_name(name)
    if not p.exists():
        return p
    stem, suffix, n = p.stem, p.suffix, 1
    while True:
        q = folder / f"{stem} ({n}){suffix}"
        if not q.exists():
            return q
        n += 1


def make_proof(code: str, nonce: str, name: str, size: int, sha: str) -> str:
    return hmac.new(code.encode(), f"{nonce}|{name}|{size}|{sha}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def default_dir() -> Path:
    return Path.home() / "Downloads" / "SayMy Drop"


# ------------------------------------------------------------------ receiver
class DropServer:
    def __init__(self, dest: Path = None, name: str = None, port: int = PORT, code: str = None,
                 max_bytes: int = MAX_BYTES, host: str = "0.0.0.0", on_receive=None, ttl: int = 600):
        self.dest = Path(dest or default_dir())
        self.name = name or socket.gethostname()
        self.code = code or new_code()
        self.max_bytes, self.ttl, self.on_receive = max_bytes, ttl, on_receive
        self.nonces, self.failures, self.received = {}, 0, []
        self.lock = threading.Lock()
        self.expires = time.time() + ttl if ttl else None
        self._publisher = None
        self._timer = None
        self.httpd = ThreadingHTTPServer((host, port), self._handler())

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def locked(self) -> bool:
        return self.failures >= MAX_FAILURES

    def start(self):
        self.dest.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if self.ttl:
            self._timer = threading.Timer(self.ttl, self.stop)
            self._timer.daemon = True
            self._timer.start()
        if not be.demo() and not os.environ.get("SAYMY_NO_AVAHI"):
            try:
                self._publisher = subprocess.Popen(["avahi-publish", "-s", self.name, SERVICE, str(self.port)],
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                self._publisher = None          # discovery is optional; typing the address still works
        return self

    def stop(self):
        if self._timer:
            self._timer.cancel()
        if self._publisher:
            self._publisher.terminate()
        threading.Thread(target=lambda: (self.httpd.shutdown(), self.httpd.server_close()), daemon=True).start()

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, status, obj):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path != "/hello":
                    return self.reply(404, {"error": "not found"})
                if server.locked:
                    return self.reply(423, {"error": "locked after too many wrong codes"})
                nonce = secrets.token_hex(16)
                with server.lock:
                    now = time.time()
                    server.nonces = {k: v for k, v in server.nonces.items() if v > now}
                    server.nonces[nonce] = now + NONCE_SECONDS
                self.reply(200, {"app": "saymy-drop", "version": 1, "name": server.name, "nonce": nonce})

            def do_POST(self):
                if self.path != "/drop":
                    return self.reply(404, {"error": "not found"})
                if server.locked:
                    return self.reply(423, {"error": "locked after too many wrong codes"})
                h = self.headers
                try:
                    size = int(h.get("Content-Length", ""))
                    name = urllib.parse.unquote(h.get("X-Drop-Name", ""))
                    sha, nonce, proof = h.get("X-Drop-Sha256", ""), h.get("X-Drop-Nonce", ""), h.get("X-Drop-Proof", "")
                except ValueError:
                    return self.reply(400, {"error": "bad request"})
                with server.lock:
                    valid_nonce = server.nonces.pop(nonce, 0) > time.time()
                good = valid_nonce and hmac.compare_digest(proof, make_proof(server.code, nonce, name, size, sha))
                if not good:
                    with server.lock:
                        server.failures += 1
                    return self.reply(403, {"error": "wrong code"})
                if size > server.max_bytes:
                    return self.reply(413, {"error": "file too large"})
                server.dest.mkdir(parents=True, exist_ok=True)
                part = server.dest / f".drop-{secrets.token_hex(6)}.part"
                digest, got = hashlib.sha256(), 0
                try:
                    with open(part, "wb") as fh:
                        while got < size:
                            chunk = self.rfile.read(min(CHUNK, size - got))
                            if not chunk:
                                break
                            fh.write(chunk)
                            digest.update(chunk)
                            got += len(chunk)
                    if got != size:
                        part.unlink(missing_ok=True)
                        return self.reply(400, {"error": "transfer interrupted"})
                    if digest.hexdigest() != sha:
                        part.unlink(missing_ok=True)
                        return self.reply(422, {"error": "file was damaged in transfer"})
                    final = unique_path(server.dest, name)
                    part.rename(final)
                except OSError as exc:
                    part.unlink(missing_ok=True)
                    return self.reply(500, {"error": str(exc)})
                server.received.append(final)
                if server.on_receive:
                    server.on_receive(final)
                self.reply(200, {"ok": True, "saved_as": final.name})

        return Handler


# ------------------------------------------------------------------ sender
def _json(resp):
    try:
        return json.loads(resp.read().decode() or "{}")
    except ValueError:
        return {}


def hello(host: str, port: int = PORT, timeout: int = 5) -> dict:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", "/hello")
        r = conn.getresponse()
        data = _json(r)
        if r.status != 200:
            raise DropError(data.get("error", "receiver refused"), r.status)
        return data
    except OSError as exc:
        raise DropError(f"could not reach {host}: {exc}")
    finally:
        conn.close()


def send_file(path, host: str, port: int, code: str, progress=None, timeout: int = 60) -> dict:
    path = Path(path)
    size = path.stat().st_size
    sha = sha256_file(path)
    info = hello(host, port)
    name = safe_name(path.name)
    proof = make_proof(code, info["nonce"], name, size, sha)
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.putrequest("POST", "/drop")
        for k, v in (("Content-Length", str(size)), ("X-Drop-Name", urllib.parse.quote(name)), ("X-Drop-Sha256", sha),
                     ("X-Drop-Nonce", info["nonce"]), ("X-Drop-Proof", proof)):
            conn.putheader(k, v)
        conn.endheaders()
        sent = 0
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(CHUNK), b""):
                conn.send(chunk)
                sent += len(chunk)
                if progress:
                    progress(sent, size)
        r = conn.getresponse()
        data = _json(r)
        if r.status != 200:
            raise DropError(data.get("error", "send failed"), r.status)
        return data
    except OSError as exc:
        raise DropError(f"transfer failed: {exc}")
    finally:
        conn.close()


# ------------------------------------------------------------------ discovery
def _unescape(s: str) -> str:
    return re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1))), s)


def parse_avahi(text: str) -> list:
    """Parse `avahi-browse -rpt _saymydrop._tcp` (IPv4 only, duplicates merged)."""
    out, seen = [], set()
    for line in text.splitlines():
        f = line.split(";")
        if len(f) < 9 or f[0] != "=" or f[2] != "IPv4":
            continue
        item = {"name": _unescape(f[3]), "host": f[6], "address": f[7], "port": int(f[8])}
        key = (item["name"], item["address"])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def find_devices() -> list:
    if be.demo():
        return [{"name": "Grace’s laptop", "host": "grace.local", "address": "192.168.1.23", "port": PORT},
                {"name": "Lab PC 4", "host": "labpc4.local", "address": "192.168.1.41", "port": PORT}]
    ok, out = be.run(["avahi-browse", "-rpt", SERVICE], 8)
    return parse_avahi(out) if ok else []


def parse_target(text: str):
    """'192.168.1.23' or '192.168.1.23:53317' -> (host, port)"""
    text = text.strip()
    if ":" in text:
        host, _, port = text.rpartition(":")
        if port.isdigit():
            return host, int(port)
    return text, PORT


# ------------------------------------------------------------------ command line
def notify(title: str, body: str = ""):
    """Desktop notification; silently skipped where notify-send is not installed."""
    try:
        subprocess.run(["notify-send", "-a", "Drop", "-i", "saymy", title, body], check=False)
    except OSError:
        pass


def cli(argv) -> int:
    if not argv or argv[0] not in ("receive", "send", "find"):
        return -1                                   # caller opens the window
    cmd = argv[0]
    if cmd == "find":
        for d in find_devices():
            print(f"{d['name']}  {d['address']}:{d['port']}")
        return 0
    if cmd == "receive":
        ttl = int(argv[argv.index("--ttl") + 1]) if "--ttl" in argv else 600
        dest = Path(argv[argv.index("--dir") + 1]) if "--dir" in argv else None
        srv = DropServer(dest=dest, ttl=ttl,
                         on_receive=lambda p: notify("File received", p.name)).start()
        print(f"Drop is on. Pairing code: {srv.code}   (port {srv.port}, switches off in {ttl // 60} minutes)")
        notify("Drop is on", f"Pairing code {srv.code}")
        try:
            while srv.expires and time.time() < srv.expires and not srv.locked:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        srv.stop()
        return 0
    # send
    try:
        path = argv[1]
        host, port = parse_target(argv[argv.index("--to") + 1])
        code = argv[argv.index("--code") + 1]
    except (IndexError, ValueError):
        print("usage: saymy-drop send FILE --to HOST[:PORT] --code 123456")
        return 2
    try:
        r = send_file(path, host, port, code, progress=lambda s, t: print(f"\r{100 * s // max(t, 1)}%", end="", flush=True))
    except DropError as exc:
        print(f"\nCould not send: {exc}")
        return 1
    print(f"\nSent. Saved on the other computer as {r['saved_as']}")
    return 0
