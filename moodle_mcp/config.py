"""Settings, read from ~/.moodle-mcp/config.json and environment variables.

Environment variables win over the file, so the MCP client config can override
anything without editing files. Nothing here is LSE-specific except the default
base URL — point MOODLE_BASE_URL at any Moodle site and the rest still works.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

HOME_DIR = Path(os.environ.get("MOODLE_MCP_HOME", Path.home() / ".moodle-mcp")).expanduser()

# The "service" shortname every Moodle site ships for its official mobile app.
# It exposes the read functions we need and is enabled on LSE Moodle.
MOBILE_SERVICE = "moodle_mobile_app"


@dataclass
class Settings:
    # LSE Moodle by default; override with MOODLE_BASE_URL for any other site.
    base_url: str = "https://moodle.lse.ac.uk"
    # Where downloaded files land: <root>/<Course short name>/<path in course>. Unless set, that's SlideMate's
    # library (its first slides folder), so synced slides show up there; without SlideMate, ~/MoodleFiles.
    download_dir: Path | None = None
    # The installed Google Chrome is used for the sign-in window; "" = bundled Chromium.
    browser_channel: str = "chrome"
    home: Path = HOME_DIR

    @property
    def token_path(self) -> Path:
        return self.home / "token.json"

    @property
    def profile_dir(self) -> Path:
        return self.home / "browser-profile"

    @property
    def ws_endpoint(self) -> str:
        return f"{self.base_url}/webservice/rest/server.php"

    @property
    def launch_url(self) -> str:
        return f"{self.base_url}/admin/tool/mobile/launch.php"


def slidemate_library() -> Path | None:
    """The first slides folder in SlideMate's settings, if SlideMate is set up on this Mac."""
    data = Path(os.environ.get("SLIDEMATE_DATA") or Path.home() / "Library/Application Support/SlideMate")
    try:
        roots = json.loads((data / "config.json").read_text()).get("library_roots") or []
    except (OSError, ValueError):
        return None
    return next((Path(r).expanduser() for r in roots if r), None)


def load_settings() -> Settings:
    s = Settings()
    cfg_path = HOME_DIR / "config.json"
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text())
        for key, value in data.items():
            if key == "download_dir":
                s.download_dir = Path(value).expanduser()
            elif hasattr(s, key):
                setattr(s, key, value)

    env = os.environ
    if env.get("MOODLE_BASE_URL"):
        s.base_url = env["MOODLE_BASE_URL"].rstrip("/")
    if env.get("MOODLE_DOWNLOAD_DIR"):
        s.download_dir = Path(env["MOODLE_DOWNLOAD_DIR"]).expanduser()
    if env.get("MOODLE_BROWSER_CHANNEL") is not None:
        s.browser_channel = env["MOODLE_BROWSER_CHANNEL"]

    if s.download_dir is None:
        s.download_dir = slidemate_library() or Path.home() / "MoodleFiles"
    s.home.mkdir(parents=True, exist_ok=True)
    return s
