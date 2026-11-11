# tea: UI and visual design

All values here come from `assets/design-tokens.json`. The QSS in `assets/theme.qss.tmpl` implements them. If a number here and the token file disagree, the token file wins.

## 1. Design plan

**Subject:** a quiet desktop tool for one writer, used in short bursts (a popup at login, a weekly focus, a Friday draft) and in longer sessions (editing a draft).

**Concept: steeping.** A week is a cup of tea. On Monday the liquid is pale jade. By Friday at 6 pm it has steeped to deep oolong brown, and the draft is ready. This is the one memorable element, and it lives in one place: a ring on the "This week" screen. Everything else is deliberately calm so the ring and the writing are what you notice.

**Color (named, light mode):**

| Name | Hex | Role |
|---|---|---|
| Celadon mist | `#E4ECE5` | App background |
| Porcelain | `#F8FAF7` | Panels and the nav rail |
| Pu-erh ink | `#1B2420` | Text |
| Matcha | `#4F7A3A` | Primary actions, focus ring, selected state |
| Oolong | `#B5701F` | Steep ring mid-tones, "weak" verification |
| Hibiscus | `#9C2F54` | The one attention color: failures, "unsupported", tray dot |

Dark mode ("Night pot") uses the same roles on `#141A17` with lighter matcha `#8DBB6F`. Full values are in the token file. Body text contrast must be at least 4.5:1 in both modes.

**Steep gradient:** jade `#DCE8CF` at 0, golden `#E8C46A` at 0.35, oolong `#B5701F` at 0.7, pu-erh `#5A3517` at 1. It is used only by the steep ring and the small steep bar in the tray menu.

**Type:**

- **UI: Instrument Sans.** Clean, slightly humanist, with weight range for hierarchy.
- **Reading and display: Newsreader.** A serif designed for screen reading. Used for the draft, the focus text, popup questions and the wordmark.
- The two are clearly different on purpose: sans for controls, serif for words that matter.
- Fallbacks: Noto Sans, Ubuntu, sans-serif / Noto Serif, Liberation Serif, serif.
- Sizes (px): caption 12, body 14, title-s 16, title-m 20, display 30, reading body 19, reading h1 34, h2 25, h3 20. Reading line-height 1.65, UI 1.45. Reading column maximum 680 px (about 66 characters).

**Fonts must be bundled.** Fetch both families (SIL Open Font License) from the `google/fonts` repository (under `ofl/instrumentsans` and `ofl/newsreader`), place the regular, italic and variable or weight files in `assets/fonts/` with their license texts, and register them at startup with `QFontDatabase.addApplicationFont`. If a font fails to load, fall back silently and log a warning. `tea doctor` reports which font actually resolved.

**Layout concept:** a left rail with four destinations and one content area. Content is left-aligned. Panels are porcelain on celadon with a 1 px line border and a soft green-tinted shadow, never a grey drop shadow. Corner radii are not uniform: 14 px panels, 8 px controls, 18 px for the floating popup, pill chips.

**Principles:**

1. One bold thing (the ring). Everything else is quiet.
2. Serif for words the owner will read or write, sans for everything they click.
3. Status is always text plus color plus an icon, never color alone.
4. No decoration: no gradients on surfaces, no eyebrow labels, no all-caps labels, no numbering except where the content really is a sequence (question 3 of 9).
5. Motion only in response to an action, plus one settle animation when a draft becomes ready.

**Review against defaults.** The first idea was a warm cream background with a terracotta accent, which is the most common "tea" look and a generic default. It was replaced with a cool celadon base, a matcha primary and hibiscus as the single hot color. Section labels in small caps and "01, 02, 03" numbering were dropped. Buttons carry plain verbs, with no arrow glyphs.

## 2. Window and navigation

- Default 1120 x 740, minimum 900 x 600. Remembers size and position.
- Left rail, 208 px wide, porcelain, 1 px right border. Top: icon plus the wordmark "tea" in Newsreader 24 semibold. Below, four items, in this order, each a `QPushButton[nav=true]` with a 20 px icon:
  1. This week
  2. New blog
  3. Drafts
  4. Settings
- Rail footer: a small status line in muted caption text, for example "Automation on" or "Paused". Clicking it toggles pause.
- Keyboard: `Ctrl+1` to `Ctrl+4` switch screens, `Ctrl+N` opens New blog, `Ctrl+Shift+C` copies the open draft for Medium, `Esc` closes popups, `Ctrl+Return` submits the current popup question.

## 3. Screens

### 3.1 This week

```
+------------+-------------------------------------------------------+
| [cup] tea  |  This week                                            |
|            |                                                       |
| > This week|   +------------------+   Focus                        |
|   New blog |   |                  |   Why small teams ship faster  |
|   Drafts   |   |   (steep ring)   |   than big ones                |
|   Settings |   |   2 days 4 hrs   |   (Newsreader 30)              |
|            |   |   until prompt   |   Picked by tea [Why?] [Change]|
|            |   +------------------+   [ Edit focus ]               |
|            |                                                       |
|            |   +--------------------------------------------------+|
|            |   | Carried over: "Last week's post"                 ||
|            |   | An improvement prompt is prepared on Friday.     ||
|            |   | [ Open draft ]   [ Shelve ]                      ||
|            |   +--------------------------------------------------+|
|            |   +--------------------------------------------------+|
|            |   | Questions this week          4 answered          ||
|            |   | [ Answer a few questions ] [ What Claude will be told ]||
|            |   +--------------------------------------------------+|
| Automation |                                                       |
| on         |                                                       |
+------------+-------------------------------------------------------+
```

- "Picked by tea" appears only when the focus came from pick mode. **Why?** lists the candidates Claude shortlisted, their angles, reasons and links (links open in the browser). **Change** opens the focus dialog.
- The carried-over card appears only when a carried-over draft exists.
- **What Claude will be told** opens a read-only preview of the answers section exactly as it will appear in the prompt, with a link to Settings to edit style notes.

**Steep ring** (`ui/widgets/steep_ring.py`, custom `QWidget`, painted with `QPainter`):

- 240 x 240 px. Track: 14 px stroke in `line`. Arc: 14 px stroke, round caps, clockwise from 12 o'clock, painted with a `QConicalGradient` using the steep stops, so the arc itself shows jade to oolong.
- Progress = (now minus Monday 00:00) / (Friday prompt time minus Monday 00:00), clamped 0 to 1. Repaint once a minute.
- Centre text: remaining time in Newsreader 28 ("2 days 4 hours", "3 hours 10 min"), with "until your prompt" in muted caption below.
- **States:**
  - *No focus:* dashed track, centre "No focus yet", primary button "Set focus". Thursday morning before pick mode starts, caption "tea will ask Claude to pick a topic at 9 am".
  - *Pick mode:* steeping as normal, centre as normal, a chip "Claude will pick the topic" under the ring.
  - *Steeping:* as above.
  - *Prompt ready:* ring full in oolong, centre "Prompt ready", primary button "Open hand-off". Caption "Waiting for Claude's reply" once the prompt has been copied.
  - *Ready:* ring full in pu-erh, centre "Draft ready", primary button "Open draft".
  - *Paused:* muted track only, centre "Paused".
- Settle animation: when the state changes to Prompt ready or Ready, the arc animates from its current length to full over 450 ms, ease-out. This is the only non-user-triggered motion. Skip it when reduce motion is on.
- Accessibility: set `accessibleName` to a sentence ("Prompt due Friday 6 pm, 2 days 4 hours left").

**Focus text** is Newsreader display (30 px). Empty state shows muted "Set a focus on Monday and tea prepares your prompt for Friday. If you don't, tea asks Claude to pick a trending topic."

### 3.2 New blog

A single scrolling form in a panel, max width 720 px:

```
New blog

Topic                         [ single line input                      ]
What should it cover?         [ multi-line, 4 rows                     ]
Who is it for? (optional)     [ single line                            ]

Sources Claude may use
[x] My documents   [ ] Web   [ ] Academic papers

+- Drop files here or choose files ---------------------------------+
|  Any file. Up to 20 files, 50 MB each. You attach them in Claude. |
+-------------------------------------------------------------------+
  report-2025.pdf   42 MB   [ Leave out ] [ Remove ]
  notes.docx                [ Leave out ] [ Remove ]

Length   ( Short ) ( Standard ) ( Long )

                                          [ Cancel ] [ Start questions ]
```

- If a scope session is in progress, a banner at the top reads "You have a blog in progress: <topic>" with **Resume**. If a hand-off is waiting, "A prompt is waiting for Claude's reply" with **Open hand-off**.
- The dropzone has a dashed 1.5 px border in `line`, turns `primary` with `primary_soft` fill on drag-over. Large files show a progress bar while copying.
- "Leave out" keeps the file stored but removes it from the "attach these" list (shown with a muted "Not listed" chip).
- First time a file is added, an inline notice (not a modal): "tea only stores these. You attach them to the Claude chat yourself."
- "Start questions" is disabled until Topic has text.

### 3.3 Drafts

Two panes. Left, 300 px: a list grouped by Waiting for Claude, Ready, Carried over, Posted and Shelved, with title, date and a status chip. Right: the draft view, or the hand-off dialog's summary for items waiting for a reply.

```
+------------------+--------------------------------------------------+
| Waiting          |  [Ready]   Why small teams ship faster           |
|   This week...   |  Friday 6:02 pm - 1,184 words - 6 min read       |
|   Prompt ready   |  [ Copy for Medium ]  Copy Markdown  Edit  More  |
| Ready            |  Version 2 (Improved)  v                         |
| > Why small...   |  ------------------------------------------------ |
|   Fri 6:02 pm    |                                                  |
| Carried over     |      Why small teams ship faster                 |
|   Last week's... |      (Newsreader 19 / 1.65, 680 px column)       |
| Posted           |  ...                         +-- Check before   --+|
|   Roads and...   |                              |   posting          ||
+------------------+                              +--------------------+|
```

- **Actions row:** primary **Copy for Medium**; quiet buttons **Copy Markdown**, **Edit**, **Regenerate**; **More** menu with **Second-pass check**, **Mark as posted**, **Shelve** or **Revive**, **Export .md**, **Delete**.
- **Regenerate** and **Second-pass check** open the hand-off dialog with a fresh prompt.
- After Copy for Medium, a muted line: "Copied. Mark as posted when it's live."
- A **version picker** appears with more than one version. Each entry shows the number and a chip (New, Improved, Regenerated, Checked); "Edited" shows if the owner edited it. Improved versions show the "What changed" list from Claude at the top of the drawer.
- **Edit** swaps the reading pane for a Markdown editor in the same serif and size. Autosave every 2 seconds to `edited_markdown`. **Preview** returns. A muted line shows "Edited. The imported draft is kept."
- **Check before posting** is a right drawer, 320 px, toggled by a button; open by default for new drafts:
  1. *Checklist* (three unenforced checkboxes): "I've edited this in my own words", "I've checked the flagged claims", "I've kept or edited the AI disclosure line".
  2. *Claims* grouped by verdict, each with icon, word and claim: check mark **Supported**, half circle **Weak**, cross **Unsupported**. Clicking a claim scrolls to and highlights it in the draft.
  3. *Sources*: title and publisher, filename and page for attached files, link for web sources (opens in the browser).
  4. *Notes from Claude*: the flags list, for example "I couldn't search the web".
  5. *Import notes*: parse warnings in plain words (section 8).
  6. *Medium formatting*: warnings if any.
  7. A toggle **Add AI disclosure line when copying** with an editable line.
- Empty state: "No drafts yet. Your first prompt is ready on Friday, or start one from New blog."

### 3.4 Settings

A single scrolling column in panels with plain headings (Title-s, semibold, sentence case):

- **Schedule:** focus day and time (Monday 09:00); pick mode day and time (Thursday 09:00); prompt day and time (Friday 18:00).
- **Topic:** switch "Ask Claude to pick a topic if I haven't set one by Thursday"; interests (editable chips); region (optional).
- **Questions:** questions per login (0 to 5, default 3); pause after dismissal (2 hours).
- **Carry-over:** "Keep unused drafts for N more weeks" (0 to 3, default 1).
- **Reminders:** switch "Remind me at login until I've pasted Claude's reply".
- **Hand-off:** Claude chat link (default `https://claude.ai/new`); include my style notes (on); style notes (multi-line text box with a muted hint: "Anything about how you write that the questions don't cover"); maximum answers in a prompt (words).
- **Writing:** default length, AI disclosure line on or off, disclosure wording.
- **Appearance:** Light, Dark, System; Reduce motion (defaults from the desktop setting).
- **Data:** Open data folder, Open log folder, Export backup (zip of DB and uploads).
- **Automation:** a single switch, "Pause all automation".
- **About:** version, and **Run checks** which shows `tea doctor` output in a read-only dialog.

### 3.5 Hand-off dialog

A centered, non-modal `QDialog`, 680 px wide, opened by the notification, the ring button, the Drafts list, New blog and the tray. Title: "Write this week's draft" (or "Write your draft", "Improve last week's draft", "Check this draft").

```
Write this week's draft
Why small teams ship faster

1  Copy the prompt
   1,420 words                                [ Copy prompt ]
   Attach these files in Claude:
   report-2025.pdf  [ Show in folder ]
   notes.docx       [ Show in folder ]

2  Open Claude                                [ Open Claude ]
   Turn on web search in Claude if you want it to research.

3  Paste Claude's reply
   +----------------------------------------------------------+
   |  (large text area, 12 rows, Ctrl+V)                      |
   +----------------------------------------------------------+
   [ Paste from clipboard ]                    [ Import draft ]
```

- The numbers are a real sequence, so numbering is allowed here. Each step has a done state (check icon) once its action happened: prompt copied, Claude opened, reply imported.
- **Copy prompt** puts plain text on the clipboard, shows a toast "Prompt copied" and marks the hand-off `copied`.
- The prompt can be previewed read-only through a quiet "View prompt" link.
- **Import draft** is disabled until the text box has content. After importing, the dialog shows a summary: title, word count, "N claims to check", and any import notes (for example "The reply had no verification section"). Buttons: **Open draft** (primary), **Paste a different reply**.
- In pick mode, step 3 also shows the chosen topic after import: "Claude picked: <topic>".
- If the reply was cut off or malformed: a calm inline message and the recovery buttons from `SPEC.md` section 3.3.
- The dialog survives being closed: the hand-off stays in Drafts under Waiting.

## 4. Floating question popup

Used for login questions, week questions and the 5 to 15 manual scope questions.

```
+--------------------------------------------------+
| Question 3 of 9                          Later   |
|                                                  |
| Who is the one reader you picture while you      |
| write this?                       (Newsreader 22)|
|                                                  |
| [ input: text / choices / 1-5 scale ]            |
|                                                  |
| Skip    Back                         [ Next ]    |
+--------------------------------------------------+
```

- A frameless, translucent-background `QWidget` with flags `Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`, containing a `QWidget#PopupCard` (radius 18, 1 px line border, green-tinted shadow of 24 px blur, offset 0 8).
- Width 460 px; height fits content (min 240, max 520). Positioned at the bottom-right of the primary screen with a 24 px margin. **On Wayland the compositor decides placement**; do not fight it.
- Drag by the header using `windowHandle().startSystemMove()`. This works on Wayland and X11.
- **Not modal.** The owner can keep working. It never steals keyboard focus while they are typing elsewhere: show with `setAttribute(Qt.WA_ShowWithoutActivating)` for login prompts; give it focus only when the owner clicks it. For the manual scope session (which the owner started), it takes focus.
- **Inputs by kind:** `text`: multi-line, 3 rows, grows to 6. `choice`: vertical radio list, each option a full-width row. `scale`: five segmented buttons with the low and high labels under the ends.
- **Buttons:** primary **Next** (**Done** on the last question), quiet **Skip**, quiet **Back** (hidden on the first), top-right quiet **Later** (closes, saves progress, does not count as skipped). `Ctrl+Return` is Next.
- The progress text reads "Question 3 of 9" for scope sessions and "Question 1 of 3" for login. Here the numbering is a real sequence, so it is allowed.
- Entry animation: 160 ms fade plus 8 px rise. No other motion.
- Login prompts auto-close after 90 seconds of no interaction and count as dismissed.

### Focus dialog (Monday to Wednesday)

A centered `QDialog` (not frameless), 520 px wide: title "What's the focus this week?", Newsreader 22; a multi-line input; a muted line "If you don't set one, tea asks Claude to pick a trending topic on Friday."; buttons **Not now** (quiet) and **Set focus** (primary). When a carried-over draft exists, a second muted line: "Last week's draft is kept and improved with this week's answers."

## 5. Tray and notifications

- Tray icon: `tea.svg`. When a prompt is ready, a reply is waiting to be pasted, or a draft is ready, switch to `tea-attention.svg` (hibiscus dot) until the owner opens the app.
- Tray menu: Open tea, Answer questions now, New blog, Open hand-off (when one is waiting), a disabled line showing time to the next prompt ("Prompt due Fri 6:00 pm"), Pause automation (checkable), Quit.
- Notification copy (title / body / action):
  - "Your draft prompt is ready" / the working title or topic / **Open hand-off**
  - "Two prompts are ready" / both titles / **Open hand-off** (when two are ready within 5 minutes)
  - "Still waiting for Claude's reply" / the title / **Open hand-off** (reminder, at most once per 2 hours)
  - "What's the focus this week?" / "Set it and tea prepares your prompt for Friday." / **Set focus**
  - "No focus yet" / "Friday's prompt will ask Claude to pick a trending topic." / **Set my own topic** (pick mode starts, sent once)
  - "No focus set" / "Nothing was prepared this week." / **Set focus** (pick switch off)
  - "Improvement prompt ready" / title of the carried-over draft / **Open hand-off**

## 6. Components

| Component | Spec |
|---|---|
| Primary button | Matcha fill, primary ink text, 8 px radius, 8 x 16 padding, weight 600 |
| Secondary button | Raised surface, 1 px line border, hover border matcha |
| Quiet button | No border, muted text, soft matcha background on hover |
| Danger button | Hibiscus text and 1 px hibiscus border, no fill |
| Focus ring | 2 px matcha border on every focusable control; never remove it |
| Status chip | Pill, caption size, text always present: Scoping, Prompt ready, Ready, Carried over, Posted, Shelved |
| Panel | Porcelain, 1 px line, radius 14, 20 px padding, tinted shadow on raised panels only |
| Toast | Bottom-center, 3 s, raised surface, one plain sentence ("Copied for Medium") |

## 7. Icons

20 px grid, 1.75 px stroke, rounded caps, drawn as SVG files in `assets/icons/` and recolored through the theme: week (cup), new blog (plus in a page), drafts (stack), settings (sliders), check, half-circle (weak), cross, copy, edit, external link, chevron, drag handle, clock, pause. Draw them by hand to match; do not pull in an icon font.

## 8. Voice and microcopy

Rules: sentence case everywhere, plain verbs, active voice, no emoji, no exclamation marks, no "Oops". An action keeps one name through its whole flow. Errors state what happened and what to do, without apologizing.

| Situation | Text |
|---|---|
| Copy for Medium | "Copied for Medium" |
| After copying | "Copied. Mark as posted when it's live." |
| Prompt copied | "Prompt copied" |
| Web search hint | "Turn on web search in Claude if you want it to research." |
| Attach files | "Attach these files in Claude:" |
| First file added | "tea only stores these. You attach them to the Claude chat yourself." |
| File too large | "report.pdf is over 50 MB. Choose a smaller file or split it." |
| Too many files | "A blog can have up to 20 files. Remove one to add another." |
| Waiting for reply | "Waiting for Claude's reply" |
| Import summary | "Imported <title>: 1,184 words, 6 claims to check." |
| Parse: no draft tag | "The reply had no draft section, so tea used the whole reply as the draft. Check the start and end." |
| Parse: no verification | "The reply had no verification section. You can copy a prompt that asks Claude to add one." |
| Parse: truncated | "The reply looks cut off at the end. You can copy a prompt asking Claude to continue." |
| Parse: unknown status | "Some claims had an unclear status and are marked as weak." |
| Pick mode, no topic in reply | "Type the topic Claude chose, so tea can file the draft under it." |
| Claude couldn't search | "Claude said it couldn't search the web. Check the claims before posting, or set your own topic." |
| No questions left | "You've answered every question for now. New ones arrive with next week's focus." |
| Empty drafts | "No drafts yet. Your first prompt is ready on Friday, or start one from New blog." |
| Auto topic | "Picked by tea because you hadn't set a focus." |
| Auto topic note on a draft | "Topic picked by tea. No answers were given for this focus." |
| Carried over | "Carried over from last week. An improvement prompt is prepared on Friday." |
| Shelved | "Shelved. tea won't prepare anything for this draft unless you revive it." |
| Disclosure notice | "Medium asks writers to disclose AI-written text. tea adds a disclosure line when you copy." |

## 9. Accessibility and quality floor

- Full keyboard operation, visible focus on every control, logical tab order.
- Contrast at least 4.5:1 for text in both themes (verify the matcha, muted and hibiscus pairs against their backgrounds).
- Respect `Reduce motion`: read the GNOME `enable-animations` gsetting at start and expose it in Settings.
- Minimum hit area 32 x 32 px for any clickable control.
- Honor system text scaling: define sizes in px through the theme but multiply by `QGuiApplication.primaryScreen().logicalDotsPerInch() / 96`, or use `QFont.setPointSizeF` conversions, so HiDPI and large-text settings work.
- Test both themes and a 125% scale.
