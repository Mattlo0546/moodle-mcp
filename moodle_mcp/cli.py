"""Command line: `moodle-mcp login | status | courses | sync | serve`."""
from __future__ import annotations

import argparse
import json
import sys

from .auth import browser_login
from .config import load_settings
from .moodle import LoginRequired, Moodle, MoodleError


def cmd_login(args) -> int:
    s = load_settings()
    print(f"Opening a browser window — sign in to {s.base_url} with your university account and MFA…")
    res = browser_login(s, headless=False, timeout_s=args.timeout)
    print(json.dumps(res, indent=1))
    return 0 if res.get("ok") else 1


def cmd_status(args) -> int:
    s = load_settings()
    try:
        info = Moodle(s).site_info()
    except LoginRequired as e:
        print(e)
        return 2
    print(f"Signed in as {info.get('fullname')} ({info.get('username')}) on {info.get('sitename')}")
    print(f"Site: {s.base_url} · downloads → {s.download_dir}")
    return 0


def cmd_courses(args) -> int:
    s = load_settings()
    try:
        for c in Moodle(s).courses():
            print(f"  {c.get('shortname'):<20} {c.get('fullname')}")
    except LoginRequired as e:
        print(e)
        return 2
    return 0


def cmd_sync(args) -> int:
    from . import server  # reuse the tools' logic
    import anyio
    import time
    rep = anyio.run(server.moodle_sync, args.course or "")
    last = None
    while rep.get("running"):  # every course: follow the background job
        if rep.get("progress") != last:
            print(rep.get("progress"), flush=True)
            last = rep.get("progress")
        time.sleep(1)
        rep = anyio.run(server.moodle_sync_status)
    print(json.dumps(rep, indent=1))
    return 2 if rep.get("login_required") else (1 if rep.get("error") else 0)


def main() -> None:
    p = argparse.ArgumentParser(prog="moodle-mcp")
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("login"); sp.add_argument("--timeout", type=int, default=300); sp.set_defaults(fn=cmd_login)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("courses").set_defaults(fn=cmd_courses)
    sp = sub.add_parser("sync"); sp.add_argument("course", nargs="?", help="omit to pull every current course's PDFs")
    sp.set_defaults(fn=cmd_sync)
    sub.add_parser("serve")
    args = p.parse_args()
    if args.cmd in (None, "serve"):
        from .server import main as serve
        serve()
        return
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
