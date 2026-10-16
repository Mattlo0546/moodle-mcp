# Moodle MCP

An [MCP](https://modelcontextprotocol.io) server that gives AI tools ([SlideMate](https://github.com/Mattlo0546/slidemate),
Claude Desktop, Claude Code, Codex) read-only access to a student's **Moodle**: courses, materials, links and
deadlines. It can also **download every course's lecture slides** into one folder per course.

It defaults to **LSE Moodle** (`https://moodle.lse.ac.uk`) but works with any Moodle site: set `MOODLE_BASE_URL`.
It uses Moodle's official mobile web-services API (the one the Moodle app uses), so it reads data rather than
scraping pages, and sign-in goes through your university's normal SSO + MFA in a real browser window.

## Install (macOS, one command)

Paste this into Terminal. It installs [uv](https://docs.astral.sh/uv/) (which brings its own Python, so you don't
need Xcode or Apple's Command Line Tools), installs `moodle-mcp`, then opens Chrome so you can sign in to Moodle once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && ~/.local/bin/uv tool install --managed-python https://github.com/Mattlo0546/moodle-mcp/archive/refs/heads/main.zip && ~/.local/bin/moodle-mcp login
```

Sign-in uses Google Chrome. Without Chrome, run `~/.local/share/uv/tools/moodle-mcp/bin/playwright install chromium`
first. To update later, run the install command again with `--reinstall` after `tool install`.

## Tools

| Tool | What it does |
| --- | --- |
| `moodle_login` | Opens a browser for university SSO + MFA and saves a token. Tries a silent refresh first. |
| `moodle_status` | Who you're signed in as, which site, and where files download to |
| `moodle_courses` | Your enrolled courses, most recently used first |
| `moodle_browse` | A course's sections with materials, links, activities and due dates |
| `moodle_deadlines` | Upcoming assignments and quizzes, soonest first |
| `moodle_download` | Save one file (a `fileurl` from `moodle_browse`) |
| `moodle_sync` / `moodle_sync_status` | With no course: download the PDFs from every current course, in the background. With a course: download all of its files. |

Courses can be named loosely: `"MY452"`, `"regression"` or the course id all work. A full sync skips courses that
have ended, and files you already have.

## Use it

### [SlideMate](https://github.com/Mattlo0546/slidemate)

Settings → **Connections & sync** → *Add server…*:

- **Name:** `moodle`
- **Command:** `moodle-mcp`
- **Arguments:** `serve`

Press **Test**: it should list 8 tools. SlideMate notices `moodle_sync`, so the library's **Pull** button
downloads new slides from all your current courses, and `moodle_login` is used when the sign-in has expired. Files
go straight into SlideMate's library (its first slides folder), as `<folder>/<course>/…`, and each Moodle course
becomes a course in SlideMate. Keep **Tutor** ticked and the tutor can check your deadlines and course pages too.

### Claude Code

```bash
claude mcp add moodle -- ~/.local/bin/moodle-mcp serve
```

### Claude Desktop / other MCP clients

```json
{
  "mcpServers": {
    "moodle": { "command": "/Users/YOU/.local/bin/moodle-mcp", "args": ["serve"] }
  }
}
```

Then ask things like *"what's due this week on Moodle?"* or *"pull everything from MY452"*.

## Command line

```bash
moodle-mcp login          # sign in (opens Chrome)
moodle-mcp status         # who you're signed in as
moodle-mcp courses        # your courses
moodle-mcp sync           # PDFs from every current course
moodle-mcp sync MY452     # every file in one course
```

## Settings (all optional)

Environment variables win over `~/.moodle-mcp/config.json`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MOODLE_BASE_URL` | `https://moodle.lse.ac.uk` | Your Moodle site |
| `MOODLE_DOWNLOAD_DIR` | SlideMate's first slides folder, else `~/MoodleFiles` | Where downloads go |
| `MOODLE_BROWSER_CHANNEL` | `chrome` | Browser for sign-in; `""` uses Playwright's own Chromium |
| `MOODLE_MCP_HOME` | `~/.moodle-mcp` | Where the token and the sign-in browser profile live |

## How sign-in works

Moodle sites behind SAML single sign-on with MFA have no password a script can post. Instead this uses Moodle's
mobile-app login handshake: it opens `admin/tool/mobile/launch.php` with a random `passport`, you sign in once in the
browser, and Moodle redirects back with a signed, base64-encoded web-service token, which is decoded and saved. The
browser profile remembers the SSO session, so later refreshes usually need no clicks.

## Privacy

- **Access:** read-only. It can't submit work, post or change anything on Moodle.
- **Storage:** the token stays on your computer (`~/.moodle-mcp/token.json`, readable only by you). Delete it to sign
  out. Data goes directly between your computer and your Moodle site.

## Development

```bash
uv run --with pytest pytest     # offline tests against a fake Moodle: sync, sign-in expiry, MCP over stdio
```

MIT licensed.
