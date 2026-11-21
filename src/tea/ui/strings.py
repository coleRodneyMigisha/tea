"""Every user-facing string. Voice rules: docs/UI_DESIGN.md section 8."""

# App
APP_NAME = "tea"
WORDMARK = "tea"

# Navigation rail (UI_DESIGN 2)
NAV_WEEK = "This week"
NAV_NEW = "New blog"
NAV_DRAFTS = "Drafts"
NAV_SETTINGS = "Settings"
AUTOMATION_ON = "Automation on"
AUTOMATION_PAUSED = "Paused"
AUTOMATION_TOOLTIP = "Click to pause or resume automation"

# Screen titles
TITLE_WEEK = "This week"
TITLE_NEW = "New blog"
TITLE_DRAFTS = "Drafts"
TITLE_SETTINGS = "Settings"
FOCUS_LABEL = "Focus"

# Empty states
EMPTY_FOCUS = (
    "Set a focus on Monday and tea prepares your prompt for Friday. "
    "If you don't, tea asks Claude to pick a trending topic."
)
EMPTY_DRAFTS = "No drafts yet. Your first prompt is ready on Friday, or start one from New blog."

# Tray (UI_DESIGN 5)
TRAY_TOOLTIP = "tea"
TRAY_OPEN = "Open tea"
TRAY_ANSWER = "Answer questions now"
TRAY_NEW_BLOG = "New blog"
TRAY_OPEN_HANDOFF = "Open hand-off"
TRAY_PAUSE = "Pause automation"
TRAY_QUIT = "Quit"
TRAY_DUE = "Prompt due {when}"
TRAY_DUE_TODAY = "today"

# Microcopy (UI_DESIGN 8)
COPIED_FOR_MEDIUM = "Copied for Medium"
AFTER_COPY = "Copied. Mark as posted when it's live."
PROMPT_COPIED = "Prompt copied"
WEB_SEARCH_HINT = "Turn on web search in Claude if you want it to research."
ATTACH_FILES = "Attach these files in Claude:"
FIRST_FILE_ADDED = "tea only stores these. You attach them to the Claude chat yourself."
FILE_TOO_LARGE = "{name} is over 50 MB. Choose a smaller file or split it."
TOO_MANY_FILES = "A blog can have up to 20 files. Remove one to add another."
COPY_FAILED = "tea couldn't copy {name}. Check that the file is still there and try again."
WAITING_FOR_REPLY = "Waiting for Claude's reply"
IMPORT_SUMMARY = "Imported {title}: {words} words, {claims} claims to check."
PARSE_NO_DRAFT = (
    "The reply had no draft section, so tea used the whole reply as the draft. "
    "Check the start and end."
)
PARSE_NO_VERIFICATION = (
    "The reply had no verification section. You can copy a prompt that asks Claude to add one."
)
PARSE_TRUNCATED = (
    "The reply looks cut off at the end. You can copy a prompt asking Claude to continue."
)
PARSE_UNKNOWN_STATUS = "Some claims had an unclear status and are marked as weak."
PICK_NO_TOPIC = "Type the topic Claude chose, so tea can file the draft under it."
CLAUDE_NO_SEARCH = (
    "Claude said it couldn't search the web. Check the claims before posting, "
    "or set your own topic."
)
NO_QUESTIONS_LEFT = (
    "You've answered every question for now. New ones arrive with next week's focus."
)
AUTO_TOPIC = "Picked by tea because you hadn't set a focus."
WHY = "Why?"
WHY_TITLE = "Why this topic?"
WHY_ANGLE = "Angle"
WHY_REASON = "Why it is trending"
WHY_SOURCES = "Sources"
AUTO_TOPIC_NOTE = "Topic picked by tea. No answers were given for this focus."
CARRIED_OVER = "Carried over from last week. An improvement prompt is prepared on Friday."
SHELVED = "Shelved. tea won't prepare anything for this draft unless you revive it."

# This week (UI_DESIGN 3.1)
SET_FOCUS = "Set focus"
SET_OWN_TOPIC = "Set my own topic"
EDIT_FOCUS = "Edit focus"
OPEN_HANDOFF = "Open hand-off"
OPEN_DRAFT = "Open draft"
CHIP_PICK = "Claude will pick the topic"
PICK_SOON = "tea will ask Claude to pick a topic at {time}"
RING_NO_FOCUS = "No focus yet"
RING_PROMPT_READY = "Prompt ready"
RING_READY = "Draft ready"
RING_PAUSED = "Paused"
RING_UNTIL = "until your prompt"
RING_SENTENCE = "Prompt due {day} {time}, {left} left"
RING_SENTENCE_NO_FOCUS = "No focus yet. Prompt due {day} {time}"
RING_SENTENCE_PICK = "Claude will pick the topic. Prompt due {day} {time}, {left} left"
RING_SENTENCE_COPIED = "Prompt ready. Waiting for Claude's reply"
DAYS = ("{n} day", "{n} days")
HOURS = ("{n} hour", "{n} hours")
MINUTES = "{n} min"
QUESTIONS_THIS_WEEK = "Questions this week"
ANSWERED = "{n} answered"
ANSWER_FEW = "Answer a few questions"
WHAT_CLAUDE_TOLD = "What Claude will be told"

# Focus dialog (UI_DESIGN 4)
FOCUS_TITLE = "What's the focus this week?"
FOCUS_HINT = "If you don't set one, tea asks Claude to pick a trending topic on Friday."
FOCUS_CARRIED = "Last week's draft is kept and improved with this week's answers."
FOCUS_SAVE = "Set focus"
FOCUS_LATER = "Not now"

# Notifications (UI_DESIGN 5)
NOTIFY_PROMPT_READY = "Your draft prompt is ready"
NOTIFY_TWO_READY = "Two prompts are ready"
NOTIFY_REMINDER = "Still waiting for Claude's reply"
NOTIFY_FOCUS = "What's the focus this week?"
NOTIFY_FOCUS_BODY = "Set it and tea prepares your prompt for Friday."
NOTIFY_PICK = "No focus yet"
NOTIFY_PICK_BODY = "Friday's prompt will ask Claude to pick a trending topic."
NOTIFY_NO_FOCUS = "No focus set"
NOTIFY_NO_FOCUS_BODY = "Nothing was prepared this week."
NOTIFY_IMPROVE_READY = "Improvement prompt ready"
NOTIFY_OPEN_HANDOFF = "Open hand-off"
NOTIFY_SET_FOCUS = "Set focus"
NOTIFY_SET_OWN_TOPIC = "Set my own topic"

# Question popup (UI_DESIGN 4)
POPUP_PROGRESS = "Question {n} of {m}"
POPUP_NEXT = "Next"
POPUP_DONE = "Done"
POPUP_SKIP = "Skip"
POPUP_BACK = "Back"
POPUP_LATER = "Later"
POPUP_LATER_TOOLTIP = "Close for now. Your answers so far are kept."
POPUP_SCALE_POINT = "{n} of 5"
POPUP_SCALE_END = "{n} of 5, {label}"

# Answers preview (SPEC 6)
PREVIEW_TITLE = "What Claude will be told about you"
PREVIEW_INTRO = "This is the answers section exactly as it appears in a prompt."
PREVIEW_EMPTY = "No answers yet. Answer a few questions and they show up here."
PREVIEW_CLOSE = "Close"

# Hand-off import
UNTITLED_DRAFT = "Untitled draft"

# tea doctor
DOCTOR_UI_FONT = "UI font: {family} ({source})"
DOCTOR_READING_FONT = "Reading font: {family} ({source})"
DOCTOR_FONT_BUNDLED = "bundled"
DOCTOR_FONT_FALLBACK = "fallback, wanted {wanted}"
DOCTOR_TRAY_OK = "Tray: available"
DOCTOR_TRAY_MISSING = "Tray: not available. Open tea from the launcher instead."

# Dates and times
WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_LONG = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
AM = "am"
PM = "pm"
DOCTOR_FONT_SYSTEM = "installed on the system"
INSTANCE_NOT_RESPONDING = "Another tea holds the lock but does not answer. Quit it and try again."

# Dropzone (UI_DESIGN 3.2)
DROP_LEAD = "Drop files here or"
DROP_CHOOSE = "choose files"
DROP_HINT = "Any file. Up to 20 files, 50 MB each. You attach them in Claude."
DROP_ACCESSIBLE = "Attached files"
CHOOSE_FILES_TITLE = "Choose files"
LEAVE_OUT = "Leave out"
INCLUDE_FILE = "Include"
REMOVE_FILE = "Remove"
NOT_LISTED = "Not listed"
SHOW_IN_FOLDER = "Show in folder"
CANCEL_COPY = "Cancel"
SIZE_MB = "{n} MB"
SIZE_KB = "{n} KB"

# Hand-off dialog (UI_DESIGN 3.5, SPEC 3)
HANDOFF_TITLES = {
    "weekly": "Write this week's draft",
    "weekly_pick": "Write this week's draft",
    "manual": "Write your draft",
    "improve": "Improve last week's draft",
    "audit": "Check this draft",
}
STEP_COPY = "Copy the prompt"
STEP_OPEN = "Open Claude"
STEP_PASTE = "Paste Claude's reply"
STEP_DONE = "Done"
PROMPT_WORDS = "{words} words"
COPY_PROMPT = "Copy prompt"
VIEW_PROMPT = "View prompt"
VIEW_PROMPT_TITLE = "The prompt"
OPEN_CLAUDE = "Open Claude"
PASTE_FROM_CLIPBOARD = "Paste from clipboard"
PASTE_SAMPLE = "Paste sample reply"
IMPORT_DRAFT = "Import draft"
PASTE_DIFFERENT = "Paste a different reply"
PASTE_ACCESSIBLE = "Claude's reply"
PASTE_PLACEHOLDER = "Paste the whole reply here, tags and all."
CLAUDE_PICKED = "Claude picked: {topic}"
COPY_AUDIT_PROMPT = "Copy a prompt asking Claude to add it"
COPY_CONTINUE_PROMPT = 'Copy a "continue" prompt'
PICK_TOPIC_PLACEHOLDER = "The topic Claude chose"
SAVE_TOPIC = "Save topic"
CLOSE = "Close"

# Drafts (UI_DESIGN 3.3)
GROUP_WAITING = "Waiting for Claude"
GROUP_READY = "Ready"
GROUP_CARRIED = "Carried over"
GROUP_POSTED = "Posted"
GROUP_SHELVED = "Shelved"
CHIP_PROMPT_READY = "Prompt ready"
CHIP_READY = "Ready"
CHIP_CARRIED = "Carried over"
CHIP_POSTED = "Posted"
CHIP_SHELVED = "Shelved"
DRAFTS_LIST = "Drafts and prompts"
DRAFT_META = "{when} - {words} words - {minutes} min read"
WAITING_SINCE = "Prompt prepared {when}"
COPY_FOR_MEDIUM = "Copy for Medium"
COPY_MARKDOWN = "Copy Markdown"
MARKDOWN_COPIED = "Markdown copied"
EDIT = "Edit"
PREVIEW = "Preview"
REGENERATE = "Regenerate"
MORE = "More"
SECOND_PASS = "Second-pass check"
MARK_POSTED = "Mark as posted"
SHELVE = "Shelve"
REVIVE = "Revive"
EXPORT_MD = "Export .md"
EXPORT_TITLE = "Export draft"
EXPORT_FILTER = "Markdown (*.md)"
EXPORT_FAILED = "tea couldn't save {name}. Choose another folder and try again."
DELETE = "Delete"
DELETE_TITLE = "Delete this version?"
DELETE_BODY = "Version {n} of {title} is removed for good. Other versions are kept."
DELETE_LAST_BODY = (
    "{title} has no other versions, so it moves to Shelved with nothing to show."
    " This can't be undone."
)
EDITED_NOTE = "Edited. The imported draft is kept."
EDITED_MARKER = "Edited"
VERSION_LABEL = "Version {n}"
VERSION_ENTRY = "Version {n} ({kind})"
VERSION_ENTRY_EDITED = "Version {n} ({kind}, edited)"
VERSION_KINDS = {
    "new": "New",
    "improved": "Improved",
    "regenerated": "Regenerated",
    "checked": "Checked",
}
DRAWER_TOGGLE = "Check before posting"
DRAWER_CHECKLIST = "Checklist"
CHECK_OWN_WORDS = "I've edited this in my own words"
CHECK_CLAIMS = "I've checked the flagged claims"
DRAWER_CHANGES = "What changed"
DRAWER_CLAIMS = "Claims"
VERDICTS = {"supported": "Supported", "weak": "Weak", "unsupported": "Unsupported"}
CLAIM_ACCESSIBLE = "{verdict}: {claim}. Press Enter to find it in the draft."
DRAWER_SOURCES = "Sources"
DRAWER_FLAGS = "Notes from Claude"
DRAWER_IMPORT_NOTES = "Import notes"
DRAWER_MEDIUM = "Medium formatting"
MEDIUM_OK = "Nothing here that Medium can't show."
MEDIUM_WARNINGS = {
    "table": "Medium has no tables. tea pastes each table row as a line of text.",
    "deep_heading": "Medium has two heading sizes. Smaller headings are pasted as subheadings.",
    "extra_h1": "Medium takes one title. Later top-level headings are pasted as headings.",
    "nested_list": "Medium can't nest lists. Nested items are pasted into the main list.",
    "raw_html": "Medium ignores HTML in a draft. tea leaves it out when copying.",
    "image": "tea leaves images out when copying. Add them in Medium.",
}
IMPORT_SUMMARY_ONE = "Imported {title}: {words} words, 1 claim to check."
HANDOFF_GONE = "This prompt's blog was deleted, so there is nothing to import into."
MONTH_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DATE_SHORT = "{day} {month}"
DATE_YEAR = "{day} {month} {year}"
CANCEL = "Cancel"
OPEN_HANDOFF_PANE = "Open hand-off"

# New blog (UI_DESIGN 3.2)
NEW_TOPIC = "Topic"
NEW_COVER = "What should it cover?"
NEW_AUDIENCE = "Who is it for? (optional)"
NEW_SOURCES = "Sources Claude may use"
SOURCE_LABELS = {"own_documents": "My documents", "web": "Web", "academic": "Academic papers"}
NEW_LENGTH = "Length"
LENGTH_LABELS = {"short": "Short", "standard": "Standard", "long": "Long"}
START_QUESTIONS = "Start questions"
IN_PROGRESS = "You have a blog in progress: {topic}"
RESUME = "Resume"
PROMPT_WAITING = "A prompt is waiting for Claude's reply"
PACKET_FAILED = "tea couldn't prepare the prompt. Press Resume to try again."
START_FAILED = "tea couldn't start the questions. Press Start questions again."
FINISH_OPEN_QUESTIONS = (
    "Finish or close the open questions first. Your form is kept, so you can start it after."
)
TRAY_RESUME = "Resume blog questions"

# M10 text (settings, backup, autostart, doctor) lives in its own file to keep this one short.
from tea.ui.strings_settings import *  # noqa: E402, F403
