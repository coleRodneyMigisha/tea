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
AUTO_TOPIC_NOTE = "Topic picked by tea. No answers were given for this focus."
CARRIED_OVER = "Carried over from last week. An improvement prompt is prepared on Friday."
SHELVED = "Shelved. tea won't prepare anything for this draft unless you revive it."

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
AM = "am"
PM = "pm"
DOCTOR_FONT_SYSTEM = "installed on the system"
INSTANCE_NOT_RESPONDING = "Another tea holds the lock but does not answer. Quit it and try again."
