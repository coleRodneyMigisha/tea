# tea build pack (for Claude Code)

This folder is everything Claude Code needs to build **tea**, a local Ubuntu desktop app that prepares blog posts for Medium.

**How tea works.** tea asks you short questions over the week. On Friday at 18:00 it has a complete, ready-to-paste **prompt** waiting. You copy it into a normal Claude chat (attaching any files yourself), paste Claude's reply back into tea, and tea turns it into a checked draft with a "Copy for Medium" button. You paste that into Medium yourself.

**No API key, no paid API, no network code.** The writing happens in your own Claude chat. tea only prepares the prompt and reads the reply you paste back.

## Set up (5 minutes)

1. Put the pack in your repo. From a normal terminal, not inside Claude Code:

   ```bash
   cd ~/Code/tea
   unzip -o ~/Downloads/tea-build-pack.zip
   git add -A && git commit -m "Add build pack" && git push
   ```

2. Install the system packages the app needs (reasons in `docs/UBUNTU_NOTES.md`):

   ```bash
   sudo apt install python3.12-venv libxcb-cursor0 libnotify-bin
   ```

3. **Restart Claude Code** in `~/Code/tea` (exit, then run `claude` again) so it loads `CLAUDE.md`, the slash commands in `.claude/commands/` and the review agents in `.claude/agents/`. Do not run `/init`; `CLAUDE.md` already exists.

4. Check `.claude/settings.json`. It pre-approves safe commands (`make`, `pytest`, `ruff`, `git add` and `commit`) and blocks `git push`, `sudo`, `rm -rf` and reading `.env` files. Adjust it if you want something different.

## How to build it

The build is 12 milestones, M0 to M11, listed in `plan/README.md`. Per milestone:

1. `/clear` (fresh context).
2. `/milestone M0` (then M1, M2, and so on, in order).
3. Claude reads its plan, then gives you a short plan and **waits**. Read it, answer any questions it asks, and say go.
4. Claude writes tests first, builds, runs `make test` and `make lint`, checks every acceptance criterion with evidence, updates `PROGRESS.md`, commits, and runs `/review`.
5. Try the result yourself with `make run`, and read the summary. If something is wrong, tell Claude and point at the doc section it missed.
6. `git push` yourself when you are happy.

### Getting the best results

- **One milestone per session.** A clean context beats a long one. `PROGRESS.md` and the plan files carry the state between sessions.
- **Use your most capable model for M2, M5 and M7** (the hand-off core, the scheduler and the hand-off dialog). Switch with `/model`. Lighter milestones are fine on a faster model.
- **Use plan mode** (Shift+Tab to cycle to it) for M2, M5, M7 and M9 so Claude cannot edit before you approve the plan.
- **UI work is checked visually.** From M3 on, Claude renders screenshots with `python -m tea.devtools.snap` and compares them to `docs/UI_DESIGN.md`. If a screen looks off to you, run the snapshot command, drag the PNG into the chat, and say what is wrong.
- **Conflicts and gaps** go to `docs/DEVIATIONS.md` via `/deviation`. Read that file after each milestone.
- **Do not let it skip ahead.** `/milestone` refuses to start if the previous milestone is not marked done.
- **Test with real writing early.** After M7, build a prompt with `tea packet`, paste it into Claude, paste the reply back, and judge the draft against `docs/WRITING_STANDARD.md`. The prompts in `prompts/` are where most of the quality comes from; tune them and bump their `version`.

## Your weekly routine once it is built

1. Monday: tell tea the week's focus. If you don't, on Thursday tea decides Claude should pick a trending topic.
2. Through the week: answer the small question popups when you log in.
3. Friday 18:00: a notification says the prompt is ready. Open the hand-off dialog, click **Copy prompt**, click **Open Claude**, attach any files it lists, turn on web search if you want research, paste the prompt, then copy Claude's reply and click **Import draft** in tea.
4. Edit the draft, use **Copy for Medium**, paste into Medium, then **Mark as posted**. If you skip a draft, tea keeps it for a week and improves it.

## What is in here

| Path | What it is |
|---|---|
| `CLAUDE.md` | Standing instructions Claude Code loads every session. Short on purpose. |
| `PROGRESS.md` | Milestone status. Claude updates it. |
| `plan/` | One file per milestone: what to read, build, test first, and the acceptance criteria. |
| `.claude/` | Slash commands (`/milestone`, `/review`, `/deviation`), two review subagents, permissions. |
| `docs/DECISIONS.md` | Your final decisions. They override everything else. |
| `docs/SPEC.md` | What the app does, workflow by workflow. |
| `docs/ARCHITECTURE.md` | Process model, modules, scheduler, hand-off layer. |
| `docs/DATA_MODEL.sql` | SQLite schema (migration 001). |
| `docs/PASTE_FORMAT.md` | The reply format Claude is asked to use and how tea parses it. |
| `docs/UI_DESIGN.md` | Visual identity, tokens, layouts, microcopy. |
| `docs/WRITING_STANDARD.md` | How the blogs must be written, and the sources behind it. |
| `docs/MEDIUM_NOTES.md` | Medium's formatting limits and AI-content policy. |
| `docs/TESTING.md`, `docs/UBUNTU_NOTES.md` | Test plan (including 22 scheduler scenarios) and Ubuntu specifics. |
| `prompts/` | The prompt templates tea fills in and puts on your clipboard. |
| `assets/` | Design tokens, QSS theme template, icons. |
| `data/` | Seed questions, question templates, starter interests. |
| `desktop/` | Launcher and autostart templates. |

## Things to know

- **Medium has an AI-content policy.** Read `docs/MEDIUM_NOTES.md`. tea gives you drafts to edit and a disclosure line on copy.
- **What you paste and attach goes to Claude.** tea itself sends nothing anywhere.
- **Claude's chat has its own limits** (message length, file sizes and counts, web search availability, usage allowance) depending on your plan. tea shows the prompt's word count; if a prompt is too long for your chat, lower the "maximum answers in a prompt" setting.
- **"Trending" means** recent coverage by at least two independent reputable publishers within 10 days, found by Claude's web search in your chat. It is not social-media analytics, and it needs web search to be on in Claude.
- **Starter interests** are in `data/interests.json`. Edit them before you build, or later in Settings.
