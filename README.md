# tea

tea is a small Ubuntu desktop app that prepares your weekly blog post for Medium. It asks you a few short questions over the week to learn how you write. On Friday at 18:00 it has a complete prompt waiting. You paste the prompt into a normal Claude chat, paste Claude's reply back into tea, and tea turns it into a checked draft with a **Copy for Medium** button. You paste the draft into Medium yourself.

tea has no API key, no paid API and no network code. It never posts anywhere. The only thing it opens is your Claude chat link, and only when you click **Open Claude**.

## Install

You need Ubuntu 24.04 or newer with Python 3.12 or newer.

```bash
sudo apt install pipx libxcb-cursor0 libnotify-bin
pipx ensurepath
cd ~/Code/tea
pipx install .
```

Open a new terminal so `tea` is on your PATH, then start it:

```bash
tea
```

Update later with `pipx install --force .` from the repo.

### Start at login

```bash
tea install-autostart
```

This writes three things, all under your home folder:

- `~/.config/autostart/tea-autostart.desktop`, which starts `tea --background` eight seconds after you log in, hidden in the tray.
- `~/.local/share/applications/tea.desktop`, so tea appears in the app launcher.
- The tea icons in `~/.local/share/icons/hicolor/scalable/apps/`.

`tea uninstall-autostart` removes exactly those files, and any folder it leaves empty.

If you do not see a tray icon, your desktop may lack the AppIndicator extension. tea still works: open it from the launcher, and a second launch brings the running window forward. `tea doctor` tells you what is missing.

## The weekly routine

1. **Monday.** tea asks for the week's focus. Type the topic you want to write about. If you skip it, tea tells Claude on Thursday to pick a trending topic near your interests.
2. **During the week.** A small popup asks up to three questions when you log in. Answer, skip or close it. **Answer a few questions** on This week opens it any time, and **What Claude will be told** shows exactly what your answers become.
3. **Friday 18:00.** A notification says the prompt is ready, also if the machine was off at 18:00. If you have not pasted a reply, tea reminds you at later logins.
4. **Write the draft** (see the next section).
5. **Edit, copy, post.** Open the draft in Drafts, edit it, press **Copy for Medium**, paste into Medium, then press **Mark as posted**.
6. **If you skip a draft.** tea keeps an unused draft for a week (change this in Settings) and prepares an improvement prompt that includes your edits and your new answers. **Shelve** keeps a draft without prompts. **Revive** brings it back. tea never deletes a draft by itself.

**New blog** prepares a prompt for any topic on demand: a short form, optional files, a few questions, then the same hand-off.

## How a hand-off works

A hand-off is the trip from tea to Claude and back. The dialog has three steps:

1. **Copy the prompt.** It goes to your clipboard as plain text. If the dialog lists files, attach them in Claude yourself. tea only stores a copy and lists it; it never reads or uploads your files.
2. **Open Claude.** This opens your Claude chat link in the browser. Turn on web search in Claude if you want it to research.
3. **Paste Claude's reply** and press **Import draft**. tea reads the reply, builds a draft and a list of claims to check, and tells you plainly if something looked wrong. A reply it could not read is kept and explained, and you can retry.

What leaves your machine is what you paste into Claude and what you attach. Nothing else.

## Settings

Everything is under Settings and saves as you change it: the schedule, pick mode and your interests, questions per login (and, if you switch it on, a question session each time you unlock your screen), how long unused drafts are kept, the Claude chat link, your style notes, light or dark, **Pause all automation**, and **Run checks**, which shows the same report as `tea doctor`.

## Back up

Settings, then Data, then **Export backup** writes a zip of the database and every stored upload. It is safe to run while tea is open.

To restore on a fresh machine, install tea, make sure it is not running, and unzip the backup into the data folder:

```bash
mkdir -p ~/.local/share/tea
unzip ~/tea-backup-2026-11-21.zip -d ~/.local/share/tea
```

Start tea; your blogs, answers, drafts and files are back. Do not unzip over a data folder you want to keep. Settings live in `~/.config/tea/settings.json`, which is small and easy to copy by hand.

Where things live:

| What | Where |
|---|---|
| Database and uploads | `~/.local/share/tea/` |
| Settings | `~/.config/tea/settings.json` |
| Log (event names only, never your writing) | `~/.local/state/tea/tea.log` |

## If something is wrong

```bash
tea doctor
```

It checks the tray, the notification service, fonts, the database, your settings, the prompt files and theme, and how much space tea uses. Each line starts with OK, WARN or FAIL, and says what to do.

Two commands help when you want to work without the window: `tea packet` prints the prompt to the terminal and `tea import-reply FILE` imports a reply saved in a file.

## Things to know

- Medium has an AI-content policy. Read `docs/MEDIUM_NOTES.md` before you post.
- Claude's chat has its own limits (message length, file sizes, web search, your plan's allowance). tea shows the prompt's word count. If a prompt is too long for your chat, lower **Maximum answers in a prompt** in Settings.
- "Trending" means recent coverage by at least two independent reputable publishers, found by Claude's web search in your chat. It is not social-media analytics.

## Developing

```bash
make setup   # venv and dev install
make run     # python -m tea
make test    # offscreen Qt tests
make lint    # ruff and mypy
```

Read `CLAUDE.md` for the rules, `PROGRESS.md` for what is built, and `docs/` for the design. Screens are rendered to PNG for review with `python -m tea.devtools.snap`.
