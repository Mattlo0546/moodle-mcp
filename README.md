# Moodle MCP

An MCP server that lets Claude pull your **Moodle** courses, materials and deadlines.
Defaults to **LSE Moodle** (`https://moodle.lse.ac.uk`) but works with any Moodle site —
just set `MOODLE_BASE_URL`.

It talks to Moodle's official **mobile web-services API** (the same one the Moodle app uses),
so it's read-only and doesn't scrape pages. Sign-in goes through your university's normal
SSO + MFA in a real browser window; a web-service token is then saved locally for reuse.

## Tools Claude gets

| Tool | What it does |
|------|--------------|
| `moodle_login` | Opens a browser for university SSO + MFA, saves a token. Tries a silent refresh first. |
| `moodle_status` | Who you're signed in as, which site, where files download to. |
| `moodle_courses` | Your enrolled courses, most recently accessed first. |
| `moodle_browse` | A course's sections with materials, links, activities and due dates. |
| `moodle_deadlines` | Upcoming assignments/quizzes, soonest first. |
| `moodle_download` | Save one file (a `fileurl` from `moodle_browse`). |
| `moodle_sync` | Download every file in a course to `<download folder>/<course>/`. |

## Setup (for the LSE friend)

Needs Python 3.10+ and Google Chrome.

```bash
cd moodle-mcp
uv venv .venv && uv pip install -e .      # or: python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m playwright install chromium   # only if Chrome isn't installed
.venv/bin/moodle-mcp login                # sign in once with your LSE account + MFA
.venv/bin/moodle-mcp courses              # confirm it worked
```

Then add it to your MCP client. For **Claude Desktop**
(`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/absolute/path/to/moodle-mcp/.venv/bin/moodle-mcp",
      "args": ["serve"]
    }
  }
}
```

For **Claude Code**: `claude mcp add moodle /absolute/path/to/moodle-mcp/.venv/bin/moodle-mcp serve`.

Restart the client, then ask Claude things like *"what's due this week on Moodle?"* or
*"pull everything from MY452 into a folder"*. If the token ever expires, Claude will say
sign-in is needed — just ask it to run `moodle_login` again (usually a silent refresh, no window).

## Configuration

Everything has a sensible default; override via environment variables (these win over the config file)
or `~/.moodle-mcp/config.json`.

| Variable | Default | Meaning |
|----------|---------|---------|
| `MOODLE_BASE_URL` | `https://moodle.lse.ac.uk` | Your Moodle site. |
| `MOODLE_DOWNLOAD_DIR` | `~/MoodleFiles` | Where `moodle_download` / `moodle_sync` save files. |
| `MOODLE_BROWSER_CHANNEL` | `chrome` | Browser for sign-in; `""` uses Playwright's bundled Chromium. |
| `MOODLE_MCP_HOME` | `~/.moodle-mcp` | Where the token and browser profile live. |

The token is stored at `~/.moodle-mcp/token.json` (chmod 600). Delete that file to sign out.

## How sign-in works

LSE Moodle uses SAML SSO with MFA, so there's no password to post from a script. Instead this
uses Moodle's mobile-app login handshake: it opens `admin/tool/mobile/launch.php` with a random
`passport`, you sign in once in the browser, and Moodle redirects back with a signed, base64-encoded
web-service token which is decoded and saved. The browser profile remembers the SSO session, so
later refreshes usually need no clicks.
