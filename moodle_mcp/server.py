"""MCP server exposing a Moodle site (LSE by default) to Claude."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP

from .auth import browser_login
from .config import load_settings
from .moodle import LoginRequired, Moodle, MoodleError

mcp = FastMCP(
    "moodle",
    instructions=(
        "Tools for the user's Moodle (LSE by default; set MOODLE_BASE_URL for another site). "
        "moodle_courses lists enrolled courses; moodle_browse shows a course's sections, materials "
        "and links; moodle_download / moodle_sync save files locally; moodle_deadlines lists upcoming "
        "assignments and quizzes. If any tool reports that sign-in is needed, call moodle_login, which "
        "opens a browser window for the university SSO + MFA and saves a web-service token."
    ),
)

_settings = load_settings()


def _mo() -> Moodle:
    return Moodle(_settings)


async def _run(fn, *args):
    try:
        return await anyio.to_thread.run_sync(lambda: fn(*args))
    except LoginRequired as e:
        return {"login_required": True, "message": str(e)}
    except MoodleError as e:
        return {"error": str(e)}


def _text(html: str | None) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def _when(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _module(m: dict) -> dict:
    out = {
        "id": m.get("id"),
        "name": m.get("name"),
        "type": m.get("modname"),
        "url": m.get("url"),
        "description": _text(m.get("description"))[:500] or None,
    }
    files = []
    for c in m.get("contents") or []:
        if c.get("type") == "file":
            files.append({
                "filename": c.get("filename"),
                "fileurl": c.get("fileurl"),
                "size": c.get("filesize"),
                "modified": _when(c.get("timemodified")),
            })
    if files:
        out["files"] = files
    if m.get("dates"):
        out["dates"] = [{"label": d.get("label"), "when": _when(d.get("timestamp"))} for d in m["dates"]]
    return {k: v for k, v in out.items() if v}


@mcp.tool()
async def moodle_login(timeout_seconds: int = 300) -> dict:
    """Sign in to Moodle. Opens a Chrome window on the user's Mac at the university sign-in page;
    the user completes SSO + MFA there and a web-service token is saved for the other tools.
    Tries a silent refresh first, so it often finishes without any window."""
    def go():
        res = browser_login(_settings, headless=True)
        if res.get("ok"):
            res["how"] = "refreshed silently"
            return res
        res = browser_login(_settings, headless=False, timeout_s=timeout_seconds)
        res["how"] = "interactive sign-in"
        return res
    return await _run(go)


@mcp.tool()
async def moodle_status() -> dict:
    """Check the Moodle session: which site, signed in as whom, and the download folder."""
    def go():
        info = _mo().site_info()
        return {
            "base_url": _settings.base_url,
            "site": info.get("sitename"),
            "signed_in_as": info.get("username"),
            "name": info.get("fullname"),
            "download_dir": str(_settings.download_dir),
        }
    return await _run(go)


@mcp.tool()
async def moodle_courses() -> list[dict] | dict:
    """List the user's enrolled Moodle courses (most recently accessed first)."""
    def go():
        return [{
            "id": c.get("id"),
            "shortname": c.get("shortname"),
            "fullname": c.get("fullname"),
            "last_accessed": _when(c.get("lastaccess")),
            "url": f"{_settings.base_url}/course/view.php?id={c.get('id')}",
        } for c in _mo().courses()]
    return await _run(go)


@mcp.tool()
async def moodle_browse(course: str) -> dict:
    """Show a course's sections with their materials, links and activities. `course` can be a
    course id, short name, or part of the full name."""
    def go():
        mo = _mo()
        c = mo.find_course(course)
        sections = []
        for sec in mo.course_contents(c["id"]):
            mods = [_module(m) for m in sec.get("modules") or []]
            sections.append({
                "section": sec.get("name"),
                "summary": _text(sec.get("summary"))[:400] or None,
                "items": [m for m in mods if m],
            })
        return {"course": c.get("shortname") or c.get("fullname"), "id": c["id"],
                "sections": [s for s in sections if s["items"] or s["summary"]]}
    return await _run(go)


@mcp.tool()
async def moodle_deadlines(limit: int = 20) -> list[dict] | dict:
    """List upcoming assignments, quizzes and other dated activities, soonest first."""
    def go():
        out = []
        for e in _mo().upcoming(limit):
            course = (e.get("course") or {}).get("fullname")
            out.append({
                "title": e.get("name"),
                "course": course,
                "due": _when(e.get("timesort")),
                "type": e.get("modulename"),
                "url": e.get("url"),
            })
        return out
    return await _run(go)


@mcp.tool()
async def moodle_download(fileurl: str, filename: str | None = None, subdir: str = "") -> dict:
    """Download one Moodle file. Pass the `fileurl` from a moodle_browse result; the file is saved
    under the download folder (optionally in `subdir`)."""
    def go():
        mo = _mo()
        name = filename or fileurl.split("/")[-1].split("?")[0] or "download"
        dest = _settings.download_dir / subdir / name
        n = mo.download(fileurl, dest)
        return {"saved": str(dest), "bytes": n}
    return await _run(go)


@mcp.tool()
async def moodle_sync(course: str, skip_existing: bool = True) -> dict:
    """Download every file in a course to <download folder>/<course>/. Existing files of the same
    size are skipped. Returns what was downloaded and what was skipped."""
    def go():
        mo = _mo()
        c = mo.find_course(course)
        short = re.sub(r"[/\\:]", "-", c.get("shortname") or str(c["id"]))
        root = _settings.download_dir / short
        downloaded, skipped, errors = [], [], []
        for sec in mo.course_contents(c["id"]):
            for m in sec.get("modules") or []:
                for cont in m.get("contents") or []:
                    if cont.get("type") != "file" or not cont.get("fileurl"):
                        continue
                    rel = (cont.get("filepath") or "/").strip("/")
                    dest = root / rel / (cont.get("filename") or "file")
                    size = cont.get("filesize") or 0
                    if skip_existing and dest.exists() and dest.stat().st_size == size:
                        skipped.append(str(dest))
                        continue
                    try:
                        mo.download(cont["fileurl"], dest)
                        downloaded.append(str(dest))
                    except Exception as e:  # noqa: BLE001 - report per-file, keep going
                        errors.append(f"{dest.name}: {e}")
        return {"course": short, "folder": str(root), "downloaded": len(downloaded),
                "skipped": len(skipped), "files": downloaded, "errors": errors}
    return await _run(go)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
