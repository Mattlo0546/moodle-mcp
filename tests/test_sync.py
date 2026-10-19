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

# Two current courses (one with a sub-folder, a .docx and a poster), an info site and one that ended last year.
COURSES = [
    {"id": 13, "shortname": "LSELIFE", "fullname": "LSE Life", "lastaccess": NOW, "enddate": 0, "visible": 1,
     "enrolledusercount": 9000},
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
            11: [{"name": "Week 1", "modules": [{"contents": [f(11, "Lecture 1.pdf"), f(11, "Notes.docx")]},
                                                {"name": "LSE100 poster", "contents": [f(11, "image.pdf")]}]},
                 {"name": "Student support", "modules": [{"contents": [f(11, "Wellbeing services.pdf")]}]},
                 {"name": "Week 2", "modules": [{"contents": [f(11, "Lecture 2.pdf", "/slides/")]}]}],
            12: [{"name": "Intro", "modules": [{"contents": [f(12, "Supply and demand.pdf")]}]}],
            9: [{"name": "Old", "modules": [{"contents": [f(9, "old.pdf")]}]}],
            13: [{"name": "Skills", "modules": [{"contents": [f(13, "Essay writing.pdf")]}]}],
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
    assert rep["skipped_courses"] == [{"id": 13, "name": "LSE Life", "why": rep["skipped_courses"][0]["why"]}]
    assert "LSE Life" in rep["summary"] and rep["not_study_files"] == 1  # the poster (the support section isn't looked at)
    assert _sync_all()["downloaded"] == 0  # a second run skips what's there


def test_student_can_bring_back_a_skipped_course():
    _token("good")
    anyio.run(server.moodle_set_courses, ["LSE Life"], None)
    listed = {c["id"]: c for c in anyio.run(server.moodle_courses)}
    assert listed[13]["synced"] and not listed[9]["synced"]
    rep = _sync_all()
    assert (LIBRARY / "LSELIFE" / "Essay writing.pdf").exists() and not rep["skipped_courses"]
    anyio.run(server.moodle_set_courses, None, ["13", "EC100"])
    listed = {c["id"]: c for c in anyio.run(server.moodle_courses)}
    assert not listed[13]["synced"] and listed[12]["why_not"] == "you turned it off"
    anyio.run(server.moodle_set_courses, ["EC100"], None)


def test_relevance_keeps_lectures_whose_topic_sounds_like_admin():
    from moodle_mcp import relevance as r
    assert r.is_study_file("Lecture 3 - Mathematical induction.pdf") and r.is_study_file("Consent in medical ethics.pdf")
    assert r.is_study_file("Survey methods L4.pdf") and r.is_study_file("Financial regulation.pdf")
    assert not r.is_study_file("Extension_request_form.pdf") and not r.is_study_file("x.pdf", "Course handbook 2026")
    assert r.course_skip_reason("Community Ecology", "BIOL20003") == ""
    assert r.course_skip_reason("Economics Department UG Hub", "ECONHUB") != ""
    assert r.course_skip_reason("First Year Noticeboard", "", "", 2500) != ""


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
