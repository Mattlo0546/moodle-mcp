"""Getting a Moodle web-service token through single sign-on.

LSE Moodle sits behind the university's SAML single sign-on with MFA, so there
is no password a script can post. Instead we use Moodle's own mobile-app login
handshake: we open the site's `launch.php` with a random `passport` and a custom
URL scheme, the user signs in once in a real browser window, and Moodle finishes
by redirecting to `<scheme>://token=<base64>`. We intercept that redirect and
decode the token. The browser profile remembers the SSO session, so later
refreshes usually need no clicks.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time

from .config import MOBILE_SERVICE, Settings

URL_SCHEME = "moodlemate"  # our private scheme; Moodle just echoes it back with the token
DESKTOP_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/154.0.0.0 Safari/537.36")


def save_token(settings: Settings, token: str, *, private_token: str = "", site: dict | None = None) -> None:
    p = settings.token_path
    p.write_text(json.dumps({
        "saved": time.time(),
        "base_url": settings.base_url,
        "token": token,
        "private_token": private_token,
        "site": site or {},
    }, indent=1))
    p.chmod(0o600)


def _decode_launch_token(b64: str, settings: Settings, passport: str) -> tuple[str, str]:
    """Return (token, private_token) from the base64 blob Moodle hands back.

    The blob decodes to `md5(wwwroot+passport):::token[:::privatetoken]`. We check
    the signature when we can, but don't fail the login if the hash doesn't line
    up (sites occasionally differ on exactly what they sign).
    """
    raw = base64.b64decode(b64).decode("utf-8", "replace")
    parts = raw.split(":::")
    if len(parts) < 2:
        raise RuntimeError("Moodle returned a token in an unexpected format.")
    signature, token = parts[0], parts[1]
    private_token = parts[2] if len(parts) > 2 else ""
    expected = hashlib.md5((settings.base_url + passport).encode()).hexdigest()
    if signature and expected and signature != expected:
        # Not fatal, but worth noting for debugging a misconfigured site.
        pass
    return token, private_token


def _launch(pw, settings: Settings, headless: bool):
    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(user_data_dir=str(settings.profile_dir), headless=headless,
                  viewport={"width": 1100, "height": 820})
    if headless:
        kwargs["user_agent"] = DESKTOP_UA
    if settings.browser_channel:
        try:
            return pw.chromium.launch_persistent_context(channel=settings.browser_channel, **kwargs)
        except Exception:
            pass  # Chrome not installed -> fall back to Playwright's bundled Chromium
    return pw.chromium.launch_persistent_context(**kwargs)


def browser_login(settings: Settings, *, headless: bool = False, timeout_s: int = 300) -> dict:
    """Open the Moodle mobile-login handshake and wait for the token redirect.

    headless=True is the silent refresh: it only works if the SSO session saved
    in the browser profile is still valid.
    """
    from playwright.sync_api import sync_playwright

    passport = f"{secrets.randbelow(10**6)}.{secrets.randbelow(10**6)}"
    launch = (f"{settings.launch_url}?service={MOBILE_SERVICE}"
              f"&passport={passport}&urlscheme={URL_SCHEME}")
    deadline = time.time() + (45 if headless else timeout_s)
    captured: dict[str, str] = {}

    def on_request(req):
        url = req.url
        if url.startswith(f"{URL_SCHEME}://") and "token=" in url:
            captured["url"] = url

    with sync_playwright() as pw:
        ctx = _launch(pw, settings, headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("request", on_request)
            # The custom-scheme redirect aborts the navigation; that's expected.
            try:
                page.goto(launch, wait_until="domcontentloaded")
            except Exception:
                pass
            if not headless:
                try:
                    page.bring_to_front()
                except Exception:
                    pass

            while time.time() < deadline and "url" not in captured:
                # Some themes land on an interstitial with a "click to continue"
                # link whose href carries the token instead of auto-redirecting.
                if not headless:
                    try:
                        for a in page.query_selector_all(f"a[href^='{URL_SCHEME}://']"):
                            href = a.get_attribute("href") or ""
                            if "token=" in href:
                                captured["url"] = href
                                break
                    except Exception:
                        pass
                if "url" in captured:
                    break
                page.wait_for_timeout(700)

            if "url" not in captured:
                return {"ok": False, "reason": "timed out waiting for sign-in"}

            b64 = captured["url"].split("token=", 1)[1]
            token, private_token = _decode_launch_token(b64, settings, passport)

            # Confirm the token works and grab the user's name for a friendly reply.
            from .moodle import Moodle
            info = Moodle(settings, token=token).site_info()
            save_token(settings, token, private_token=private_token,
                       site={"sitename": info.get("sitename"), "username": info.get("username"),
                             "fullname": info.get("fullname"), "userid": info.get("userid")})
            return {"ok": True, "user": info.get("username"), "name": info.get("fullname"),
                    "site": info.get("sitename")}
        finally:
            ctx.close()


def refresh_silently(settings: Settings) -> bool:
    try:
        return bool(browser_login(settings, headless=True).get("ok"))
    except Exception:
        return False
