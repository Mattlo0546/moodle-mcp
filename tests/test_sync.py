"""Offline tests against a fake Moodle: `uv run --with pytest pytest`. No Moodle account or network needed."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import anyio

TMP = Path(tempfile.mkdtemp())
LIBRARY = TMP / "Slides"
NOW = int(time.time())

# Two current courses (one with a sub-folder and a .docx) and one that ended last year.
COURSES = [
    {"id": 11, "shortname": "MY452", "fullname": "Applied Regression", "lastaccess": NOW, "enddate": NOW + 10**7, "visible": 1},
    {"id": 12, "shortname": "EC100", "fullname": "Economics A", "lastaccess": NOW - 50, "enddate": 0, "visible": 1},
    {"id": 9, "shortname": "OLD101", "fullname": "Last year", "lastaccess": NOW - 10**8, "enddate": NOW - 10**7, "visible": 1},
]


def _body(cid, name):
    return f"%PDF-1.4 fake {cid} {name}".encode()


class FakeMoodle(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, raw):
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        q = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        fn = q["wsfunction"][0]
        if q["wstoken"][0] != "good":
            return self._send(json.dumps({"exception": "x", "errorcode": "invalidtoken", "message": "Invalid token"}).encode())
        base = f"http://127.0.0.1:{self.server.server_port}/webservice/pluginfile.php"

        def f(cid, name, path="/"):
            return {"type": "file", "filename": name, "filepath": path, "filesize": len(_body(cid, name)),
                    "fileurl": f"{base}/{cid}/{urllib.parse.quote(name)}"}
        contents = {
            11: [{"name": "Week 1", "modules": [{"contents": [f(11, "Lecture 1.pdf"), f(11, "Notes.docx")]}]},
                 {"name": "Week 2", "modules": [{"contents": [f(11, "Lecture 2.pdf", "/slides/")]}]}],
            12: [{"name": "Intro", "modules": [{"contents": [f(12, "Supply and demand.pdf")]}]}],
            9: [{"name": "Old", "modules": [{"contents": [f(9, "old.pdf")]}]}],
        }
        out = {"core_webservice_get_site_info": {"userid": 5, "fullname": "Test Student"},
               "core_enrol_get_users_courses": COURSES}.get(fn)
        if fn == "core_course_get_contents":
            out = contents[int(q["courseid"][0])]
        self._send(json.dumps(out).encode())

    def do_GET(self):
        parts = urllib.parse.urlparse(self.path).path.split("/")
        self._send(_body(parts[-2], urllib.parse.unquote(parts[-1])))


SERVER = HTTPServer(("127.0.0.1", 0), FakeMoodle)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()

(TMP / "home").mkdir()
(TMP / "slidemate").mkdir()
(TMP / "slidemate" / "config.json").write_text(json.dumps({"library_roots": [str(LIBRARY)]}))
os.environ.update(MOODLE_BASE_URL=f"http://127.0.0.1:{SERVER.server_port}", MOODLE_MCP_HOME=str(TMP / "home"),
                  SLIDEMATE_DATA=str(TMP / "slidemate"))
os.environ.pop("MOODLE_DOWNLOAD_DIR", None)


def _token(value):
    (TMP / "home" / "token.json").write_text(json.dumps({"token": value}))


from moodle_mcp import server  # noqa: E402  (reads the settings above)


def _sync_all():
    rep = anyio.run(server.moodle_sync)
    while rep.get("running"):
        time.sleep(0.1)
        rep = anyio.run(server.moodle_sync_status)
    return rep


def test_downloads_go_to_slidemate_library():
    assert server._settings.download_dir == LIBRARY


def test_sync_every_current_course_pdfs_only():
    _token("good")
    rep = _sync_all()
    files = sorted(str(p.relative_to(LIBRARY)) for p in LIBRARY.rglob("*") if p.is_file())
    assert files == ["EC100/Supply and demand.pdf", "MY452/Lecture 1.pdf", "MY452/slides/Lecture 2.pdf"]
    assert rep["downloaded"] == 3 and "2 courses" in rep["summary"] and not rep["errors"]
    assert _sync_all()["downloaded"] == 0  # a second run skips what's there


def test_one_course_gets_every_file():
    _token("good")
    rep = anyio.run(server.moodle_sync, "MY452")
    assert (LIBRARY / "MY452" / "Notes.docx").exists() and "summary" in rep


def test_expired_sign_in_is_reported():
    _token("expired")
    assert _sync_all().get("login_required") is True
    _token("good")


def test_stdio_lists_tools_and_keeps_stdout_clean():
    p = subprocess.Popen([sys.executable, "-m", "moodle_mcp.cli", "serve"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        def rpc(mid, method, params=None):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}) + "\n")
            p.stdin.flush()
            return json.loads(p.stdout.readline())  # fails if anything but JSON-RPC reaches stdout
        rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "test", "version": "0"}})
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        names = {t["name"] for t in rpc(2, "tools/list")["result"]["tools"]}
        assert {"moodle_sync", "moodle_sync_status", "moodle_login", "moodle_deadlines"} <= names
    finally:
        p.kill()
