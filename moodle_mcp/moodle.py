"""A thin client over Moodle's Web Services REST API.

Everything Moodle exposes to its mobile app goes through one endpoint,
`/webservice/rest/server.php`, with a `wstoken`, a `wsfunction` name and the
function's arguments. Arguments that are lists or dicts are flattened into
PHP's bracket notation (`courseids[0]=5`), which `_flatten` handles.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class LoginRequired(RuntimeError):
    """Raised when there is no token, or Moodle rejects the one we have."""

    def __init__(self, msg: str = ""):
        super().__init__(
            msg
            or "Not signed in to Moodle (or the token expired). Run the `moodle_login` tool "
            "(or `moodle-mcp login` in a terminal) and complete the university sign-in in the "
            "window that opens."
        )


class MoodleError(RuntimeError):
    """A web-service call returned a Moodle exception that isn't an auth problem."""


# Moodle error codes that mean "your token is no good any more".
_AUTH_ERRORS = {"invalidtoken", "invalidlogin", "accessexception", "sitemaintenance"}


def _flatten(data: Any, prefix: str = "") -> dict[str, str]:
    """Turn nested args into Moodle's flat bracket form, e.g.
    {"courseids": [5, 6]} -> {"courseids[0]": "5", "courseids[1]": "6"}.
    """
    out: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            name = f"{prefix}[{key}]" if prefix else str(key)
            out.update(_flatten(value, name))
    elif isinstance(data, (list, tuple)):
        for i, value in enumerate(data):
            out.update(_flatten(value, f"{prefix}[{i}]"))
    elif isinstance(data, bool):
        out[prefix] = "1" if data else "0"
    elif data is not None:
        out[prefix] = str(data)
    return out


class Moodle:
    def __init__(self, settings: Settings, token: str | None = None):
        self.settings = settings
        self._token = token if token is not None else self._load_token()
        self._client = httpx.Client(timeout=60.0, follow_redirects=True,
                                     headers={"User-Agent": "moodle-mcp/0.1"})

    # --- token storage ---
    def _load_token(self) -> str:
        import json
        p = self.settings.token_path
        if not p.exists():
            return ""
        try:
            return json.loads(p.read_text()).get("token", "")
        except (json.JSONDecodeError, OSError):
            return ""

    @property
    def token(self) -> str:
        return self._token

    # --- the one call everything goes through ---
    def call(self, wsfunction: str, **args: Any) -> Any:
        if not self._token:
            raise LoginRequired()
        params = {
            "wstoken": self._token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
        }
        params.update(_flatten(args))
        resp = self._client.post(self.settings.ws_endpoint, data=params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("exception"):
            code = payload.get("errorcode", "")
            msg = payload.get("message", "Moodle error")
            if code in _AUTH_ERRORS:
                raise LoginRequired(f"{msg} (Moodle said: {code}).")
            raise MoodleError(f"{wsfunction}: {msg} ({code})")
        return payload

    # --- high-level helpers ---
    def site_info(self) -> dict:
        return self.call("core_webservice_get_site_info")

    def courses(self) -> list[dict]:
        """The user's enrolled courses (newest access first)."""
        me = self.site_info()
        cs = self.call("core_enrol_get_users_courses", userid=me["userid"])
        cs.sort(key=lambda c: c.get("lastaccess") or 0, reverse=True)
        return cs

    def course_contents(self, courseid: int) -> list[dict]:
        """Sections, each with its activity modules and any files they hold."""
        return self.call("core_course_get_contents", courseid=courseid)

    def upcoming(self, limit: int = 20) -> list[dict]:
        """Calendar action events (assignments, quizzes…) due from now on."""
        import time
        res = self.call(
            "core_calendar_get_action_events_by_timesort",
            timesortfrom=int(time.time()),
            limitnum=limit,
        )
        return (res or {}).get("events", [])

    def file_url(self, url: str) -> str:
        """Add the token to a pluginfile.php URL so the file can be downloaded."""
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}token={self._token}"

    def download(self, url: str, dest) -> int:
        """Stream a Moodle file to `dest`; returns bytes written."""
        from pathlib import Path
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self._client.stream("GET", self.file_url(url)) as r:
            r.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
                    written += len(chunk)
        return written

    def find_course(self, course: str) -> dict:
        """Resolve a course by id, short name or a substring of its full name."""
        courses = self.courses()
        q = str(course).strip().lower()
        for c in courses:
            if str(c.get("id")) == q:
                return c
        for c in courses:
            if (c.get("shortname") or "").lower() == q:
                return c
        for c in courses:
            if q in (c.get("fullname") or "").lower() or q in (c.get("shortname") or "").lower():
                return c
        raise MoodleError(f"No enrolled course matches {course!r}.")
