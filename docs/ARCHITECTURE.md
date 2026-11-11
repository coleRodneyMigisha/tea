# tea: architecture

## 1. Process model

One process: the **tea app**. It runs in two modes from the same binary.

- `tea` starts the app and shows the main window.
- `tea --background` starts it hidden (tray icon only). The autostart entry uses this at login.

A second launch does not start a second process. It connects to the first through a `QLocalServer` socket (`tea-ipc`) and asks it to show the main window. Use `QLockFile` in the runtime dir for single-instance.

**Why a resident app and not systemd timers:** a timer-launched process has no guaranteed Wayland/X11 session environment, so popups and notifications fail in confusing ways. A resident app already lives in the user session, shows dialogs reliably, and handles "laptop was asleep" with catch-up logic.

**No network.** tea makes no network calls of any kind. The only outward action is `QDesktopServices.openUrl` on the Claude chat link, when the owner clicks. Do not add HTTP clients, API SDKs or telemetry.

### Tray

`QSystemTrayIcon` with a menu: Open tea, Answer questions now, New blog, Pause automation, Quit. Ubuntu 24.04 shows tray icons through the AppIndicator extension; if no tray is available the app still works. Closing the main window hides it (the process keeps running). **Quit** from the tray menu exits fully.

## 2. Package layout

```
src/tea/
  __main__.py         # argument parsing, single-instance handling, app start
  app.py              # QApplication setup, wiring, tray, lifecycle
  clock.py            # Clock protocol, SystemClock, FakeClock (tests)
  config.py           # paths (platformdirs), constants, defaults
  settings.py         # pydantic Settings model, load/save (JSON in config dir)
  logging_setup.py    # rotating file log in ~/.local/state/tea/, no content logged
  db/
    connection.py     # open DB (WAL, foreign_keys=ON), migration runner
    repos.py          # WeekRepo, BlogRepo, QuestionRepo, AnswerRepo, AttachmentRepo, DraftRepo, HandoffRepo, JobRepo
  migrations/
    001_initial.sql   # copy of docs/DATA_MODEL.sql
  handoff/
    prompts.py        # load prompts/*.md and prompts/blocks/*.md, check variables, render
    packets.py        # build a packet (prompt text) for each hand-off kind from DB state
    answers.py        # build the grouped "my answers" section (newest per question, cap, ordering)
    parse.py          # lenient parser for pasted replies -> ParsedReply (docs/PASTE_FORMAT.md)
    importer.py       # turn a ParsedReply into a draft version, set pick-mode focus, update statuses
    provider.py       # Provider protocol and ManualProvider (the only provider in v1)
  domain/
    weeks.py          # week start, due datetimes from settings, ISO helpers
    questions.py      # seeding from data/, template instantiation, weighted selection, session mix, cooldown
    attachments.py    # store copies, limits (20 files, 50 MB), list for prompts
    improve.py        # week rollover: carry, shelve, most-recent-only, improvement questions
    medium.py         # Markdown -> Medium-safe HTML, plain text, warnings, disclosure insert
  scheduler.py        # job evaluation and catch-up (pure logic + Qt timer shell)
  notify.py           # DBus notifications with actions; tray fallback; coalescing
  workers.py          # QRunnable wrapper, signals, cancellation (file copying, large pastes)
  devtools/
    snap.py           # renders screens and states to PNG (see M3); dev only
    sample_data.py    # fixtures: blogs, answers, a sample well-formed reply, a malformed reply
  ui/
    theme.py          # render QSS + QPalette from tokens, load fonts
    strings.py        # every user-facing string
    main_window.py
    screens/          # this_week.py, new_blog.py, drafts.py, settings.py
    widgets/          # steep_ring.py, question_popup.py, focus_dialog.py, handoff_dialog.py, chip.py,
                      # dropzone.py, markdown_view.py, markdown_editor.py, toast.py
tests/
```

## 3. Threading

- The GUI thread never does slow work. Copying large attachments and building very large packets run in `workers.run(fn, *args, on_done, on_error, on_progress)` on `QThreadPool`, with results by signal. Each worker opens its own SQLite connection (WAL lets the GUI read while a worker writes).
- Parsing a pasted reply is fast but runs in a worker if the reply exceeds 200 KB.

## 4. Scheduler

Split in two so it can be tested without Qt.

**Pure logic** (`scheduler.py: evaluate(now, state) -> list[Action]`). Given the current time and database state it returns the actions due: `ShowFocusDialog(week)`, `EnterPickMode(week)`, `PreparePacket(kind, week or blog)`, `ShowLoginQuestions`, `RemindHandoff(handoff)`, `NotifyNoFocus(week)`, `Rollover(week)`. Deterministic; uses the injected `Clock`.

**Qt shell** (`SchedulerRunner`). Calls `evaluate` at app start, every 60 seconds, and on resume from sleep (a wall-clock gap greater than 5 minutes between ticks, or `org.freedesktop.login1.Manager.PrepareForSleep(false)`).

### Job rules

State lives in the `jobs` and `handoffs` tables keyed so every action is idempotent.

| Kind | Due when | Done when | Notes |
|---|---|---|---|
| `focus_prompt` | now >= Monday `focus_time`, no focus, and not in pick mode | focus saved | Re-show at each login and wake; 2-hour pause after dismissal. Not pushed once pick mode starts; "Set my own topic" stays available. |
| `pick_mode` | now >= Thursday `pick_time`, no focus, pick switch on | `weeks.pick_mode = 1` and notification sent | Same week only. Creates the week row and the blog (topic `''`, `topic_origin = auto_trending` pending). |
| `weekly_packet` | now >= Friday `draft_time` of week W; focus set or pick mode on; no non-superseded handoff for W | handoff row created (`prompt_ready`) and notification sent | Also evaluated for week W-1 (catch-up up to 7 days). Kind is `weekly` or `weekly_pick`. |
| `improve_packet` | now >= Friday `draft_time` and a carried-over, unshelved blog exists | `improve` handoff created | Runs after `weekly_packet` in the same pass. |
| `no_focus_notice` | now >= Friday `draft_time`, no focus, not in pick mode | notified once | Pick switch off case. |
| `login_questions` | app start, cooldown elapsed, `questions_per_login` > 0 | session completed or dismissed | Once per app start. |
| reminder | a handoff is `prompt_ready` or `copied`, at app start or wake, `reminders` on | `reminder_count` and `last_reminder_at` updated | At most one reminder per 2 hours and never while the hand-off dialog is open. |

Changing the focus after a pick-mode prompt was prepared marks that handoff `superseded` and prepares a normal `weekly` handoff. Regenerate marks the current handoff `superseded` and prepares a new one.

### Week rollover

On the first `evaluate` in a new ISO week (guarded by a `meta` key `rollover_done_<week_start>`), for the previous week's weekly blogs with status `ready` and no `copied_at` or `posted_at` on any version: increment `carried_weeks`. If `carried_weeks` is greater than `settings.carry_over_weeks`, set status `shelved`; otherwise keep it `ready` and add the improvement questions. If more than one blog is a candidate, only the most recent carries; older ones are shelved.

### Pause

"Pause all automation" makes `evaluate` return nothing except manual actions.

Required scenarios are in `TESTING.md`.

## 5. Hand-off layer

```python
class Provider(Protocol):
    def deliver(self, packet: Packet) -> None: ...      # ManualProvider: shows the hand-off dialog
class ManualProvider(Provider): ...                      # v1: the owner copies, pastes into Claude, pastes the reply back
```

Keep this interface so an automated provider could be added later. Do not implement one.

- **Packets:** `packets.build(kind, blog_id|week) -> Packet(text, words, kind, prompt_versions, attachments)`. It assembles: the brief; the grouped answers section (`answers.py`); style notes; the attachments section from `blocks/attachments.md` when files exist; the pick section from `blocks/pick_topic.md` in `weekly_pick`; the research section from `blocks/research_on.md` or `research_off.md` according to the blog's allowed sources (research on when Web or Academic is allowed); the length in words; and `topic_origin_note` ("Topic picked by tea. No answers were given for this focus." when relevant). Optional sections render as empty strings; do not leave blank-line runs (collapse three or more newlines to two).
- **Answers section:** group by category in this order: voice, audience, structure, evidence, experience, boundaries, then scope and improve for this blog. Within a group, the newest answer per question, skipped excluded, each line `Q: ... / A: ...`. Cap at about 6,000 words, dropping the oldest first but never dropping boundaries answers. For `improve`, `new_answers` holds only answers given after the previous version's `imported_at`.
- **Prompt rendering** raises on an unfilled or unexpected variable. Versions go to `handoffs.prompt_versions`.
- **Import:** `importer.import_reply(handoff_id, text) -> ImportResult` parses (`parse.py`), creates a new `drafts` row (version = max + 1, kind from the handoff kind), stores raw reply, warnings, claims, sources, flags and changes, sets blog status `ready`, marks the handoff `imported`, and in pick mode sets the week's `focus_text`, `topic_origin = auto_trending`, the blog's topic and title, and stores `trend_candidates`. Importing never throws on a bad reply; it returns warnings.
- **Parser rules** are in `docs/PASTE_FORMAT.md`.

## 6. Attachments

tea does **not** read, extract or upload files. `attachments.add(blog_id, path)` copies the file to `~/.local/share/tea/uploads/<blog_id>/`, stores its name, extension and size, and enforces **20 files per blog and 50 MB per file** with the messages in `UI_DESIGN.md` section 8. The hand-off dialog lists included files with "Show in folder" so the owner can drag them into the Claude chat. Copying a large file runs in a worker with progress.

## 7. Medium output (`domain/medium.py`)

- `markdown_to_medium_html(md, disclosure: str | None) -> str` using `markdown-it-py` with tables disabled. H1 becomes the title; H2 and H3 only. Return a list of warnings for anything Medium handles poorly (tables, H4 and below, nested lists, raw HTML, images).
- `to_plain_text(md)` for the plain half of the clipboard.
- Clipboard: a `QMimeData` with both `text/html` and `text/plain`, set on `QGuiApplication.clipboard()`.
- Disclosure insertion: one paragraph after the first or second body paragraph, never before the title.

## 8. Notifications

`QtDBus` call to `org.freedesktop.Notifications.Notify` with actions `["default", "Open"]`, listening for `ActionInvoked`. Map the returned id to a callback. If the service is missing or the call fails, fall back to `QSystemTrayIcon.showMessage`. Reuse the notification id for the same hand-off so reminders replace rather than stack.

## 9. Settings

`settings.json` in `~/.config/tea/`, validated by a pydantic model with defaults. Unknown keys are ignored. Fields: focus day and time, pick day and time and on/off, prompt day and time, interests and region (seeded from `data/interests.json`), questions per login, pause after dismissal, carry-over weeks, reminders on/off, Claude chat URL, include style notes, style notes text, maximum answer words in a packet, default length, disclosure on/off and wording, appearance, reduce motion, pause automation. There is no API key or model setting.

## 10. Logging

Rotating file at `~/.local/state/tea/tea.log`, 1 MB x 3, INFO level. Event names and ids only; never answers, drafts, pasted replies or file names.

## 11. Packaging

Dev: `make setup && make run`. Daily use: `pipx install .` from the repo, then `tea install-autostart`, which renders `desktop/tea.desktop` and `desktop/tea-autostart.desktop` (replacing `__TEA_BIN__` with the absolute path from `shutil.which("tea")`) into `~/.local/share/applications/` and `~/.config/autostart/`, and installs the icon under `~/.local/share/icons/hicolor/scalable/apps/`. `tea uninstall-autostart` removes them.

## 12. CLI

```
tea                          # start, show window
tea --background             # start hidden (autostart)
tea packet [--week YYYY-MM-DD] [--kind weekly|weekly_pick|improve]   # print a packet to stdout (dev)
tea import-reply FILE [--handoff ID]      # import a reply from a file (dev and recovery)
tea login-questions          # show the question popup now
tea install-autostart | uninstall-autostart
tea doctor                   # checks tray, notification service, fonts, DB, templates, prompts
```
