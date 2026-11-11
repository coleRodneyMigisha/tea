# tea: testing

## 1. Principles

- No test touches the network. tea has no network code; a test greps `src/` for `anthropic`, `requests`, `httpx`, `urllib.request` and `socket` imports and fails if any are found (the only allowed outward call is `QDesktopServices.openUrl`).
- No test calls the system clock. Use `FakeClock`.
- GUI tests run headless with `QT_QPA_PLATFORM=offscreen` and `pytest-qt`.
- Each test builds its own temporary data directory and database.
- Prefer testing pure logic (scheduler `evaluate`, week helpers, question selection, packet building, the reply parser, Medium conversion) over testing widgets.
- Fixtures for replies live in `devtools/sample_data.py`: a well-formed reply for each hand-off kind, plus malformed ones (see section 3).

## 2. Scheduler scenarios (all required, written against `FakeClock`)

Times are local. Defaults: focus Monday 09:00, pick mode Thursday 09:00, prompt Friday 18:00, reminder pause 2 hours, carry-over 1 week.

1. **Normal week.** Focus set Monday 09:05, app running. At Friday 17:59 nothing is prepared. At 18:00 `PreparePacket(weekly)` is emitted once, a handoff exists with status `prompt_ready`, and one notification is sent. Re-evaluating emits nothing.
2. **App off at Friday 18:00,** started Saturday 10:00: the packet is prepared at start and the notification is sent then.
3. **Laptop asleep** Friday 17:30 to 21:15 (clock jump): on resume the packet is prepared.
4. **Focus prompt.** Dismissed Monday 09:10: not shown again before 11:10; shown at the next login or wake after 11:10. Not pushed after pick mode starts.
5. **Pick mode.** No focus at Thursday 09:00: `EnterPickMode` is emitted once, the week row has `pick_mode = 1`, one notification is sent. At Friday 18:00 the packet kind is `weekly_pick`.
6. **Pick mode with machine off** Wednesday to Friday 20:00: at start, pick mode is entered and the packet is prepared in the same pass, in that order.
7. **Focus after pick mode.** Owner sets a focus Thursday 09:30 (or Friday 17:00, or after the packet exists): the pick-mode handoff is marked `superseded`, a normal `weekly` packet is prepared at the right time (or immediately if Friday 18:00 has passed), and pick mode ends. Owner sets a focus at Thursday 08:59: no pick mode at all.
8. **Pick switch off.** No focus, switch off: no pick mode; at Friday 18:00 `NotifyNoFocus` is emitted once and no packet is prepared.
9. **Reminders.** A `prompt_ready` handoff, app restarted 3 hours later: one reminder at start. A second start 1 hour later: no reminder (2-hour pause). Never a reminder while the hand-off dialog is open, none after `imported`, none when reminders are off.
10. **Week boundary.** Sunday 23:59 to Monday 00:01 changes the active week; last week's jobs are not duplicated; an un-imported handoff from last week stays valid and keeps its reminders.
11. **Carry-over.** Week W draft is `ready`, never copied or posted. At the first evaluate in W+1: `carried_weeks` becomes 1, status stays `ready`, improvement questions are added once. At Friday 18:00 of W+1, `PreparePacket(improve)` is emitted after the weekly packet (if a focus exists). At the first evaluate in W+2 with the draft still unused: status becomes `shelved`.
12. **Used drafts do not carry.** A draft with `copied_at` or `posted_at` set is not carried and gets no improvement packet.
13. **Carry-over limit.** With the setting at 0, an unused draft is shelved at rollover. With 2, it carries twice and shelves at the third rollover.
14. **Only the most recent carries.** Two unused ready drafts at rollover: the newer carries, the older is shelved.
15. **Revive.** A shelved draft revived mid-week carries for one more week and gets an improvement packet next Friday.
16. **Rollover idempotency.** Evaluating ten times across the boundary carries and shelves exactly once.
17. **Regenerate.** Regenerate marks the current handoff `superseded` and creates a new one; reminders follow the new one only.
18. **Pause on:** `evaluate` returns nothing except manual actions. Pause off: due actions are emitted at the next tick.
19. **Login questions:** emitted once per app start; not emitted if `questions_per_login` is 0; not emitted within the cooldown after a dismissal.
20. **Two ticks within the same minute** produce no duplicate actions.
21. **Settings changed** (prompt time moved from 18:00 to 20:00 on Friday 19:00): the packet is prepared at 20:00, not immediately.
22. **Two packets within 5 minutes** (weekly plus improve) produce one combined notification.

## 3. Unit tests by module

| Module | Must cover |
|---|---|
| `domain/weeks` | ISO week start across year ends and leap years; due datetimes; "previous week" at boundaries |
| `domain/questions` | Seeding idempotent by `bank_key`; template instantiation (`{focus}`, `{title}`, `{topic}` filled, unknown placeholders rejected); scope-template selection by rule (5 to 15, orders, `applies` conditions); weighting; 14-day rule; cooldown; session mix; skipped stored as skipped |
| `domain/attachments` | 20-file and 50 MB limits with exact messages; copy to uploads; include/leave out; large copy runs in a worker with progress |
| `domain/improve` | Carry, shelve, revive, limit and most-recent-only rules exactly as in scheduler scenarios 11 to 16; improvement questions use the draft title |
| `domain/medium` | Tables removed or warned; heading levels capped; nested lists flattened with a warning; images warned; disclosure after the first or second body paragraph and never before the title; both clipboard MIME types |
| `handoff/prompts` | Every prompt and block loads; each header's `variables` equals its placeholders; unfilled and unexpected variables raise |
| `handoff/answers` | Grouping order; newest per question; skipped excluded; boundaries answers never dropped by the cap; `new_answers` only after the previous version's import time |
| `handoff/packets` | Each kind renders with no leftover `{{`; optional sections vanish cleanly (no runs of blank lines); research block follows allowed sources; pick block present only in `weekly_pick`; attachments block only when files are included; word count correct |
| `handoff/parse` | Well-formed reply for each kind; tags in any case; code fences around the whole reply; preamble text; missing `<draft>`; missing `<verification>`; truncated reply; pipe characters inside claims; unknown statuses; extra unknown tags; empty reply; a reply that is only a draft with no tags; a very large reply. The parser never raises. |
| `handoff/importer` | New version numbers; kind from handoff; raw reply stored verbatim; pick mode sets focus, topic, title, candidates and `topic_origin`; handoff marked imported; re-import creates a new version; blog status transitions |
| `settings` | Defaults; unknown keys ignored; invalid values rejected with a clear message |
| `db` | Migrations idempotent; cascades; unique constraints; schema matches `docs/DATA_MODEL.sql` |

## 4. GUI tests (pytest-qt)

- Question popup: keyboard-only completion of text, choice and scale questions; Back preserves answers; Later saves progress; Skip records skipped.
- Steep ring: renders without error at progress 0, 0.5, 1 and in each state; `accessibleName` set.
- Hand-off dialog: Copy prompt puts the packet on the clipboard and marks the handoff `copied`; Import is disabled with an empty box; importing the sample reply shows the summary; importing a malformed reply shows the right notes and recovery buttons; closing and reopening keeps the pasted text.
- Drafts: Copy for Medium puts `text/html` and `text/plain` on the clipboard and sets `copied_at`; Edit autosaves; version picker lists versions.
- Theme: both modes render; a test greps `src/tea/ui/` for hex color literals outside `theme.py` and fails if any are found.
- Dropzone: rejects a 51 MB file and a 21st file with the specified messages.

## 5. Manual QA checklist (on real Ubuntu 24.04, Wayland and X11)

- [ ] Fresh login: background app starts, tray icon appears, question popup appears without stealing typing focus.
- [ ] Monday focus dialog appears at first login after 09:00.
- [ ] Set the clock (or use `TEA_NOW` with `TEA_DEBUG=1`) to Friday 17:59 and watch the ring, the notification and its Open action.
- [ ] Close the laptop lid across Friday 18:00, reopen, confirm the prompt is prepared and one notification appears.
- [ ] Take a real prompt into a real Claude chat, with web search on, and attach a file. Paste the reply back. Check the import summary and the draft.
- [ ] Copy for Medium, paste into a Medium story editor, confirm headings, links and lists survive.
- [ ] Light, Dark and System themes; 100% and 125% scaling; reduce motion on and off.
- [ ] Tab through every screen using only the keyboard.
- [ ] Paste a deliberately broken reply (no tags, cut off) and confirm the recovery options.
- [ ] `tea doctor` output is accurate.

## 6. Debug aids to build in

- `TEA_NOW="2026-11-13T17:59:00"` overrides the clock, only when `TEA_DEBUG=1`.
- `tea packet --week YYYY-MM-DD --kind weekly` prints a packet to stdout.
- `tea import-reply FILE` imports a reply from a file.
- A "Paste sample reply" button in the hand-off dialog, visible only when `TEA_DEBUG=1`, fills the box from `devtools/sample_data.py` so the whole flow can be exercised without Claude.
