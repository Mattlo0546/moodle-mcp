# Moodle MCP Server: Moodle for Claude, ChatGPT Codex and Cursor

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-server-8A2BE2)](https://modelcontextprotocol.io)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![M8ven Score](https://m8ven.ai/badge/mcp/mattlo0546-moodle-mcp-1v977q?v=28369debb984625cc02b39b9640c01b6)](https://m8ven.ai/mcp/mattlo0546-moodle-mcp-1v977q?s=readme)

**moodle-mcp** is an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for
**Moodle**. It lets AI assistants (Claude Desktop, Claude Code, ChatGPT Codex, Cursor, VS Code and
[SlideMate](https://github.com/Mattlo0546/slidemate)) read a student's Moodle courses, materials, links and
deadlines. It can also **download every course's lecture slides** into one folder per course.

- **Works at any university that uses Moodle**, including UCL, King's College London (KEATS), LSE, Cambridge
  and Warwick ([full list](#universities-that-use-moodle)). It defaults to LSE (`moodle.lse.ac.uk`); set
  `MOODLE_BASE_URL` for anywhere else.
- **Uses Moodle's official mobile-app API** (the one the Moodle app uses), so it reads data rather than scraping
  pages.
- **No password or token to copy.** You sign in through your university's normal SSO and MFA in a real browser
  window.
- **Read-only.** It can't submit work, post or change anything on Moodle.

> Using Canvas or Blackboard instead? See [canvas-mcp](https://github.com/Mattlo0546/canvas-mcp) (Oxford, Harvard,
> Stanford…) and [blackboard-mcp](https://github.com/Mattlo0546/blackboard-mcp) (Imperial, Edinburgh, Bristol…).

## What you can ask

- *"What's due on Moodle this week?"*
- *"Show me what's in week 4 of MY452."*
- *"Pull everything from MY452."*
- *"Download the lecture slides from all my current modules."*

## Install (macOS / Linux, one command)

Paste this into Terminal. It installs [uv](https://docs.astral.sh/uv/) (which brings its own Python, so you don't
need Xcode or Apple's Command Line Tools), installs `moodle-mcp`, then opens Chrome so you can sign in to Moodle once.
Change `moodle.ucl.ac.uk` to your university's Moodle address:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && ~/.local/bin/uv tool install --managed-python https://github.com/Mattlo0546/moodle-mcp/archive/refs/heads/main.zip && MOODLE_BASE_URL=moodle.ucl.ac.uk ~/.local/bin/moodle-mcp login
```

Sign-in uses Google Chrome. Without Chrome, run `~/.local/share/uv/tools/moodle-mcp/bin/playwright install chromium`
first. To update later, run the install command again with `--reinstall` after `tool install`.

## Tools

| Tool | What it does |
| --- | --- |
| `moodle_login` | Opens a browser for university SSO + MFA and saves a token. Tries a silent refresh first. |
| `moodle_status` | Who you're signed in as, which site, and where files download to |
| `moodle_courses` | Your enrolled courses, most recently used first, and whether a full sync pulls each one |
| `moodle_set_courses` | Change which courses a full sync pulls (`include` an info site it skips, `exclude` a course) |
| `moodle_browse` | A course's sections with materials, links, activities and due dates |
| `moodle_deadlines` | Upcoming assignments and quizzes, soonest first |
| `moodle_download` | Save one file (a `fileurl` from `moodle_browse`) |
| `moodle_sync` / `moodle_sync_status` | With no course: download the PDFs from every current course, in the background. With a course: download all of its files. |

Courses can be named loosely: `"MY452"`, `"regression"` or the course id all work. A full sync skips courses that
have ended, and files you already have. It also skips what isn't for studying: sites that aren't courses (guidance
hubs, LSE Life, the library's skills site, year-group noticeboards) and, inside courses, posters, handbooks, forms,
timetables and the "Student support" section. Its report lists the sites it skipped; `moodle_set_courses` brings one
back. Words that are also lecture topics only count in an admin phrase, so "Mathematical induction" stays and
"Induction week schedule" goes ([`relevance.py`](moodle_mcp/relevance.py)).

## Connect it to your AI app

Set `MOODLE_BASE_URL` to your university's Moodle address in each config below.

### SlideMate

In [SlideMate](https://github.com/Mattlo0546/slidemate), go to Settings → **Your university**, then pick your
university or **Moodle** and press **Connect**. SlideMate installs this server, signs you in, and makes the
library's **Pull** button download new slides from all your current courses into your library. Nothing to type.

### Claude Code

```bash
claude mcp add moodle -e MOODLE_BASE_URL=https://moodle.ucl.ac.uk -- ~/.local/bin/moodle-mcp serve
```

### Claude Desktop

Settings → Developer → Edit Config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/Users/YOU/.local/bin/moodle-mcp",
      "args": ["serve"],
      "env": { "MOODLE_BASE_URL": "https://moodle.ucl.ac.uk" }
    }
  }
}
```

The same block works in Cursor (`~/.cursor/mcp.json`). VS Code's `.vscode/mcp.json` uses `"servers"` in place of
`"mcpServers"`.

### ChatGPT Codex CLI

```bash
codex mcp add moodle --env MOODLE_BASE_URL=https://moodle.ucl.ac.uk -- ~/.local/bin/moodle-mcp serve
```

## Universities that use Moodle

Any Moodle site with the mobile app service turned on works. Most have it on, because that's what the official
Moodle app needs. These addresses were checked to be Moodle sites:

| University | `MOODLE_BASE_URL` |
| --- | --- |
| UCL (University College London) | `moodle.ucl.ac.uk` |
| King's College London (KEATS) | `keats.kcl.ac.uk` |
| London School of Economics (LSE) | `moodle.lse.ac.uk` |
| University of Cambridge | `www.vle.cam.ac.uk` |
| University of Warwick | `moodle.warwick.ac.uk` |
| Queen Mary University of London (QMplus) | `qmplus.qmul.ac.uk` |
| Royal Holloway, University of London | `moodle.royalholloway.ac.uk` |
| University of Bath | `moodle.bath.ac.uk` |
| University of Nottingham | `moodle.nottingham.ac.uk` |
| University of Glasgow | `moodle.gla.ac.uk` |
| University of Exeter | `vle.exeter.ac.uk` |
| Loughborough University (Learn) | `learn.lboro.ac.uk` |
| University of Hong Kong | `moodle.hku.hk` |

Your university's address is the one in your browser's address bar when you open Moodle.

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

## FAQ

**Is there an MCP server for UCL Moodle or King's KEATS?**
Yes, this one. Set `MOODLE_BASE_URL` to `moodle.ucl.ac.uk` or `keats.kcl.ac.uk`. In SlideMate, pick UCL or King's
from the list.

**Do I need a Moodle API token?**
No. `moodle_login` gets one through Moodle's mobile-app sign-in, after you sign in with your university account.

**Does it work with ChatGPT?**
It works with OpenAI's Codex CLI and with any app that supports local (stdio) MCP servers. The ChatGPT website can
only use remote MCP servers.

**It says the site doesn't allow the mobile app.**
Your Moodle has the mobile web service turned off, so this server can't sign in. Only your university's Moodle
admins can turn it on.

## Privacy

- **Access:** read-only. It can't submit work, post or change anything on Moodle.
- **Storage:** the token stays on your computer (`~/.moodle-mcp/token.json`, readable only by you). Delete it to sign
  out. Data goes directly between your computer and your Moodle site.

## Development

```bash
uv run --with pytest pytest     # offline tests against a fake Moodle: sync, sign-in expiry, MCP over stdio
```

## Related

- [canvas-mcp](https://github.com/Mattlo0546/canvas-mcp): MCP server for Canvas LMS
- [blackboard-mcp](https://github.com/Mattlo0546/blackboard-mcp): MCP server for Blackboard Learn (Ultra)
- [classroom-mcp](https://github.com/Mattlo0546/classroom-mcp): MCP server for Google Classroom
- [SlideMate](https://github.com/Mattlo0546/slidemate): a free Mac app with an AI tutor that has read your whole
  lecture deck. It sets all of these up in one click.

MIT licensed. Not affiliated with Moodle Pty Ltd or any university. Moodle is a trademark of Moodle Pty Ltd.
