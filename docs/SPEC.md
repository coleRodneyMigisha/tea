# tea: product specification

Decisions in `DECISIONS.md` override this file where they differ.

## 1. What tea is

tea is a local Ubuntu desktop app that prepares blog posts for Medium. It runs quietly in the background, asks the owner a few questions over time so Claude can write in their voice, and on Friday at 18:00 it has a complete, ready-to-paste **prompt** waiting. The owner pastes the prompt into Claude, pastes Claude's reply back into tea, and tea turns it into a checked draft with a Medium-ready copy button. A second mode prepares a prompt for any blog on demand.

tea never talks to the internet itself and never posts anywhere. The only things that leave the machine are what the owner pastes into Claude, and what they paste into Medium.

Single user, single machine. No accounts, no API key, no server.

## 2. Principles

1. **Drafts, not finished posts.** Medium restricts undisclosed AI-written text (see `MEDIUM_NOTES.md`). tea produces a first draft the owner edits, and makes disclosure easy.
2. **Honest sourcing.** Every factual claim is tied to a source or flagged. The prompt forbids invented sources, quotes, statistics and anecdotes, and tea shows a verification report.
3. **The owner's voice.** Their answers go to Claude verbatim, grouped by what they are about.
4. **Quiet by default.** Popups are short, skippable and rate-limited. Reminders do not nag.
5. **Never lose work.** Every answer, prompt, pasted reply and edit is saved as it happens. Nothing is deleted automatically.
6. **Few round trips.** Each draft costs the owner one copy and one paste, not four.

## 3. The hand-off

A **hand-off** is one round trip with Claude. Kinds:

| Kind | Purpose |
|---|---|
| `weekly` | Write the week's draft from the owner's focus. |
| `weekly_pick` | Pick a trending topic near the owner's interests, then write the draft (pick mode). |
| `manual` | Write a draft for a New blog. |
| `improve` | Improve a carried-over draft using new answers and the owner's edits. |
| `audit` | Optional second pass: fact-check and tighten an existing draft. |

### 3.1 Steps (the hand-off dialog)

1. **Copy the prompt.** tea builds it from the templates in `prompts/` and shows its word count. If the blog has files, the dialog lists them: "Attach these files in Claude."
2. **Open Claude.** A button opens the configured chat link in the default browser (default `https://claude.ai/new`). A hint says: "Turn on web search in Claude if you want it to research."
3. **Paste Claude's reply** into the large text box and click **Import draft**.

tea parses the reply (format in `PASTE_FORMAT.md`), stores the raw reply, the draft, the verification report, the sources list and the flags, and shows a summary: title, word count, claims flagged, warnings about anything missing.

### 3.2 What the prompt contains

The owner's brief (topic, scope, audience, length); their answers grouped by category (voice, audience, structure, evidence, experience, boundaries), newest answer per question, skipped excluded, capped at about 6,000 words (oldest dropped first); their style notes; the list of attached files; instructions about research (use web search if available, otherwise say so and work only from attachments and answers); the writing standard condensed from `WRITING_STANDARD.md`; and the required reply format. In pick mode it also contains interests, region, today's date, topics written about in the last 8 weeks and off-limits topics.

### 3.3 If something is wrong

- Reply missing tags: tea treats the whole reply as the draft, adds a flag "No verification report in the reply", and offers **Copy a prompt asking Claude to add it** (an `audit` hand-off).
- Pick mode but no `<topic>`: tea asks the owner to type the topic Claude chose; the draft stays attached to it.
- Reply truncated (no closing tag): tea imports what it has, flags it, and offers **Copy a "continue" prompt**.
- The owner can edit the pasted text in the dialog before importing, and can re-import over a draft (it becomes a new version).

## 4. Weekly mode

Each ISO week runs Monday 00:00 to Sunday 23:59, local time. One weekly blog per week.

| When | What happens |
|---|---|
| Monday 09:00, or the first login or wake after it | A dialog asks "What's the focus this week?". |
| Monday to Wednesday | If no focus is set, the dialog returns at each login and wake, with a 2-hour pause after each dismissal. |
| As soon as a focus exists | tea adds the focus questions (templates with the focus filled in) to the question pool. |
| Every login | A small popup asks 2 to 3 questions (default 3, range 0 to 5). |
| Thursday 09:00, no focus | The week goes into **pick mode** (section 4.1). |
| Friday 18:00 | tea prepares the prompt (`weekly` or `weekly_pick`), plus an `improve` prompt for any carried-over draft, and notifies the owner. |
| After Friday 18:00 | At each login, if a prompt has not been imported, a reminder (2-hour pause between reminders, none while the dialog is open). |

### 4.1 Pick mode

- Triggered at Thursday 09:00 (or the first start or wake after) only if there is no focus and "Pick a topic for me on Thursday" is on (default on).
- tea notifies once: "No focus yet. Friday's prompt will ask Claude to pick a trending topic." with **Set my own topic**.
- Friday's `weekly_pick` prompt asks Claude to find topics being covered **now** (at least two independent reputable publishers within the last 10 days) that fit the interests, rank about five, choose one, and write the draft on it. Guardrails are in the prompt: no breaking tragedies, unverified rumors, partisan politics, celebrity gossip, topics from the last 8 weeks, or off-limits topics.
- On import, tea sets the week's focus to the chosen topic with `topic_origin = auto_trending`, stores the candidate list and its sources, and shows "Picked by tea. Why?" on the This week screen.
- "Trending" means recent, multi-source coverage found through web search. It is not social-media analytics. If Claude cannot search, it says so in the flags and the owner should set a topic.
- If the owner sets a focus before importing, the prompt is rebuilt as a normal `weekly` prompt.
- If the pick switch is off and there is no focus at Friday 18:00, tea notifies "No focus set. Nothing was prepared." with **Set focus**.

### 4.2 Carry-over and improvement

- When a new week starts, any weekly draft from the previous week that is **ready and unused** is carried over. **Used** means **Copy for Medium** or **Mark as posted** was clicked.
- Carried-over drafts stay in Drafts under "Carried over". tea adds 4 to 6 **improvement questions** (templates in `data/improve_questions.json`, with the draft title filled in) to the question pool.
- On Friday 18:00, tea prepares an `improve` prompt: the previous text (the owner's edited version if there is one), all answers given since the draft was written, and the style notes. Claude revises rather than restarts, and lists what it changed.
- A draft carried past the limit (default 1 week; setting 0 to 3) is **shelved**: kept, no more automatic work, and the owner can **Revive** it for one more week.
- Only weekly drafts carry over. Only the most recent unused draft carries; older ones are shelved.

### 4.3 Missed schedules

Catch-up, not exact-time: prompts are prepared at the first app start or wake after the due time, within 7 days. If the machine was off from Wednesday to Friday evening, at start tea enters pick mode (if needed) and prepares the prompt in the same pass.

## 5. Manual mode (New blog)

1. **Form.** Topic (required), what it should cover, who it is for, allowed source types (My documents, Web, Academic papers), attached files (up to 20, 50 MB each; tea only stores and lists them), length (Short, Standard, Long).
2. **Scope questions.** 5 to 15 questions chosen from `data/scope_question_templates.json` by rule (always-on questions first, then those that apply to the options the owner chose), shown one at a time in the floating popup. Answer, skip, go back, or "Later"; progress is saved and resumable.
3. **Hand-off.** After the last question the hand-off dialog opens with a `manual` prompt.

## 6. Questions

- **Pools:** the seed bank (`data/question_bank.json`), focus questions (`data/focus_question_templates.json`, with `{focus}` filled in), improvement questions (`data/improve_questions.json`), and manual-mode scope questions.
- **Login session mix (default 3):** one improvement question if any exist, one focus question if any exist, the rest from the bank; fill empty slots from the other pools.
- **Selection:** weighted random. Weight rises with time since last asked, falls with `asked_count`. No repeats within a session; no re-asking within 14 days unless the pool is exhausted.
- **Cooldown:** after a dismissed popup, none for 2 hours. At most one login session per app start. Login popups close after 90 seconds of no interaction and count as dismissed.
- **Skipping** is recorded as skipped.
- **Style notes:** a free-text box in Settings. The "What Claude will be told about you" preview shows the answers section exactly as it will appear in a prompt.

## 7. Draft view

- Reading pane in a serif face, 680 px maximum width, rendered from the Markdown.
- **Copy for Medium** (primary): rich text (HTML) and plain text on the clipboard. If "Add AI disclosure line" is on (default), a one-line disclosure is inserted in the first two paragraphs. Records `copied_at` ("used").
- **Copy Markdown**, **Edit** (autosave; the pasted text is kept), **Regenerate** (opens a new hand-off), **Second-pass check** (opens an `audit` hand-off), **Mark as posted**, **Shelve**, **Revive**.
- Version picker with chips (New, Improved, Regenerated, Checked) and an "Edited" marker.
- **Check before posting** drawer: verification report by status, sources, flags from Claude, Medium formatting warnings, word count and reading time, and a short checklist.

## 8. Settings

Schedule (focus, pick and prompt times), Topic (pick on Thursday on or off, interests, region), Questions (per login, pause after dismissal), Carry-over (weeks), Reminders (on or off), Hand-off (Claude chat link, include style notes, style notes text, maximum answers in a prompt), Writing (default length, disclosure on or off and wording), Appearance (Light, Dark, System; reduce motion), Data (open data and log folders, export backup), Pause all automation, About.

## 9. Notifications

Freedesktop notifications with an action button; tray message as fallback. Replace rather than stack notifications for the same hand-off. If two prompts are ready within 5 minutes, send one: "Two prompts are ready".

## 10. Privacy and data

- Everything is stored in `~/.local/share/tea/tea.db` and `~/.local/share/tea/uploads/`.
- tea makes **no network calls**. It opens the Claude link in the browser only when the owner clicks.
- What reaches Claude is what the owner pastes and attaches. The first-run notice says so.

## 11. Non-goals

Posting to Medium. API or automated Claude calls. Image generation. Multi-user support. Social-media trend analytics. Planned-blog lists or bulk import. Reading or uploading source files for the owner.

## 12. Acceptance (whole product)

- A fresh login shows the question popup; answers persist across restarts.
- With a Monday focus, a complete prompt exists at Friday 18:00 with a notification, also when the machine was off at 18:00; reminders appear at later logins until imported.
- With no focus, Thursday 09:00 puts the week in pick mode, Friday's prompt asks for a topic pick, and importing the reply sets the focus and shows why.
- Pasting a well-formed reply creates a draft with a verification report; a malformed reply is kept, explained and recoverable.
- An unused Friday draft is carried over; next Friday's `improve` prompt includes the owner's edits and new answers.
- Copy for Medium pastes cleanly into Medium's editor.
- Killing the app at any point loses nothing.
