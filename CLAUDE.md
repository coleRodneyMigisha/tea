# tea

A local Ubuntu 24.04 desktop app (Python 3.12, PySide6) that prepares blog posts for Medium. It asks the owner short questions to learn their voice, and on Friday at 18:00 it has a ready-to-paste **prompt** waiting. The owner pastes the prompt into a Claude chat, pastes Claude's reply back, and tea turns it into a checked draft with a Medium-ready copy button. The owner pastes drafts into Medium by hand. **tea has no API, no API key and no network code**; it never posts anywhere.

## How to work in this repo

1. **One milestone per session.** Milestones are in `plan/M0.md` to `plan/M11.md`. Start with `/milestone M<n>`. Read `PROGRESS.md` first to see what is done.
2. **Read only what the milestone lists.** Each plan file names the exact docs and sections to read. Do not load every doc up front.
3. **Plan, then wait.** Before editing, give a short plan (files, order, risks, anything unclear) and wait for the owner's go-ahead.
4. **Tests first.** Write the tests the plan lists, watch them fail, then implement.
5. **Verify before claiming.** Run `make test` and `make lint`. For anything visual, render it with `python -m tea.devtools.snap` (built in M3) and look at the PNG. Say plainly what you could not verify (real Wayland behavior, DBus notifications, a real Claude reply).
6. **Finish cleanly.** Update `PROGRESS.md`, make one commit per logical change, run `/review M<n>`, then summarize in under 15 lines. The owner runs `/clear` before the next milestone.

## Source of truth

| Question | File |
|---|---|
| What the app does, and every decision made | `docs/SPEC.md`, `docs/DECISIONS.md` |
| The reply format tea parses | `docs/PASTE_FORMAT.md` |
| How it is built | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.sql` |
| How it looks | `docs/UI_DESIGN.md`, `assets/design-tokens.json`, `assets/theme.qss.tmpl` |
| How blogs must be written | `docs/WRITING_STANDARD.md`, `prompts/` |
| Medium limits and AI policy | `docs/MEDIUM_NOTES.md` |
| Ubuntu specifics | `docs/UBUNTU_NOTES.md` |
| Tests | `docs/TESTING.md` |

If two docs disagree or something is missing, do not guess silently. Run `/deviation` to log it in `docs/DEVIATIONS.md` with the choice you made, and carry on with the simplest option. Never edit files in `docs/`, `plan/` or `prompts/` except `docs/DEVIATIONS.md`, unless the owner asks.

## Stack

Python 3.12, `src/tea/` layout. PySide6 only (no web views). SQLite via `sqlite3` with plain SQL migrations. `pydantic` v2 for settings. `markdown-it-py`, `platformdirs`. Dev: `pytest`, `pytest-qt`, `ruff`, `mypy`. No other runtime dependencies without asking.

## Commands

```
make setup   # venv + dev install
make run     # python -m tea
make test    # QT_QPA_PLATFORM=offscreen pytest -q
make lint    # ruff check . && ruff format --check . && mypy src/tea
make fmt     # ruff format .
```

## Rules that apply to all code

- Type hints everywhere. Modules stay under 400 lines and do one job.
- **Clock is injected.** Never call `datetime.now()` outside `tea/clock.py`.
- **No network, no API.** Never add an HTTP client, an API SDK, telemetry or a background download. The only outward action is `QDesktopServices.openUrl` on the Claude link when the owner clicks. A test enforces this.
- **The reply parser never raises.** Whatever the owner pastes, `handoff/parse.py` returns a result with warnings.
- **GUI thread never blocks.** Large file copies and other slow work run in workers (`QThreadPool`), with results returned by signal. Each worker opens its own SQLite connection.
- **All user-facing text lives in `src/tea/ui/strings.py`** and follows the voice rules in `docs/UI_DESIGN.md` section 8.
- **No hex colors, font names or pixel sizes in widget code.** Everything comes from the theme. A test enforces this.
- **Prompts are files** in `prompts/` (and `prompts/blocks/`), loaded by `tea.handoff.prompts`, and their versions are stored with every hand-off and draft. Never inline prompt text in Python.
- SQL lives in `tea/db/` only.
- Never log answers, drafts, pasted replies or file names. Log event names, ids, durations and error classes.
- tea never reads or uploads the owner's attached files. It only stores a copy and lists them.

## Boundaries

- Build only what the docs describe. No extra features, no refactors of finished milestones unless a test demands it.
- Do not push to GitHub. Do not rewrite git history.
- Do not run commands that need `sudo`; tell the owner what to run instead.
- Do not read `.env` files.

## Definition of done (every milestone)

Tests added and passing offline. `make lint` clean. The app starts with `make run`. Acceptance criteria in the plan file each checked with evidence (a test name, a command output, or a screenshot path). `PROGRESS.md` updated. Anything unverified listed honestly.
