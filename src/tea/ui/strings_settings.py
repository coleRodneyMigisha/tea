"""User-facing text for Settings, backup, autostart and `tea doctor` (re-exported by strings)."""

# Settings (UI_DESIGN 3.4)
SETTINGS_SECTIONS = {
    "schedule": "Schedule",
    "topic": "Topic",
    "questions": "Questions",
    "carry": "Carry-over",
    "reminders": "Reminders",
    "handoff": "Hand-off",
    "writing": "Writing",
    "appearance": "Appearance",
    "data": "Data",
    "automation": "Automation",
    "about": "About",
}
SETTINGS_FOCUS = "Focus"
SETTINGS_PICK = "Pick a topic"
SETTINGS_PROMPT = "Prompt"
SETTINGS_PICK_SWITCH = "Ask Claude to pick a topic if I haven't set one by Thursday"
SETTINGS_INTERESTS = "Interests"
SETTINGS_INTERESTS_HINT = "Claude uses these when it picks a topic for you."
SETTINGS_ADD_INTEREST = "Add an interest"
SETTINGS_REMOVE_INTEREST = "Remove {name}"
SETTINGS_REGION = "Region (optional)"
SETTINGS_PER_LOGIN = "Questions per login"
SETTINGS_PAUSE_AFTER = "Pause after dismissal"
SETTINGS_MINUTES = " minutes"
SETTINGS_KEEP_PREFIX = "Keep unused drafts for"
SETTINGS_KEEP_SUFFIX = "more weeks"
SETTINGS_REMINDERS = "Remind me at login until I've pasted Claude's reply"
SETTINGS_CLAUDE_LINK = "Claude chat link"
SETTINGS_INCLUDE_NOTES = "Include my style notes"
SETTINGS_STYLE_NOTES = "Style notes"
SETTINGS_STYLE_HINT = "Anything about how you write that the questions don't cover"
SETTINGS_MAX_ANSWERS = "Maximum answers in a prompt"
SETTINGS_WORDS = " words"
SETTINGS_LENGTH = "Default length"
SETTINGS_APPEARANCE = "Theme"
APPEARANCE_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}
SETTINGS_REDUCE_MOTION = "Reduce motion"
SETTINGS_OPEN_DATA = "Open data folder"
SETTINGS_OPEN_LOGS = "Open log folder"
SETTINGS_EXPORT = "Export backup"
SETTINGS_PAUSE_SWITCH = "Pause all automation"
SETTINGS_VERSION = "tea {version}"
SETTINGS_RUN_CHECKS = "Run checks"
SETTINGS_CHECKS_TITLE = "tea doctor"
SETTINGS_LOAD_ERROR = (
    "tea couldn't read settings.json, so it is running on the defaults. {detail} "
    "Change anything here and tea saves a new file; the old one is kept as settings.json.broken."
)
SETTINGS_URL_HTTPS = "The link must start with https://."
SETTINGS_URL_EMPTY = "Enter the link to open for Claude."
SETTINGS_URL_NO_SITE = "The link needs a site name after https://, with no spaces."
SETTINGS_INTEREST_DUPLICATE = "That interest is already in the list."
SETTINGS_INTEREST_LONG = "Keep an interest to 60 characters or fewer."
SETTINGS_SAVE_FAILED = "tea couldn't save that setting. Check the config folder and try again."
EXPORT_TITLE = "Export backup"
EXPORT_FILTER = "Zip files (*.zip)"
BACKUP_DONE = "Backup saved as {name}."
BACKUP_FAILED = "tea couldn't save the backup. Choose another folder and try again."
BACKUP_NO_DB = "There is no database to back up yet."
BACKUP_NOT_A_BACKUP = "That file is not a tea backup."
BACKUP_TARGET_USED = "That folder already holds a tea database. Choose an empty folder."
BACKUP_UNSAFE = "That backup holds paths outside its folder, so tea did not restore it."
BACKUP_WORKING = "Saving backup"

# Autostart
AUTOSTART_NO_BIN = (
    "Can't find the tea command. Install tea with `pipx install .` first, then run this again."
)
AUTOSTART_FAILED = "Could not write the autostart files: {error}."
AUTOSTART_INSTALLED = "Installed {count} files. tea starts hidden at your next login."
AUTOSTART_REMOVED = "Removed {count} files."

# tea doctor (M10)
DOCTOR_NOTIFY_OK = "Notifications: service reachable"
DOCTOR_NOTIFY_MISSING = (
    "Notifications: service not reachable. tea shows messages from the tray icon instead."
)
DOCTOR_DB_MISSING = "Database: not created yet. It appears when tea first starts."
DOCTOR_DB_OK = "Database: healthy, migrated to version {version}"
DOCTOR_DB_BEHIND = (
    "Database: healthy but at version {version} of {latest}. It migrates when tea starts."
)
DOCTOR_DB_NEWER = "Database: version {version} is newer than this tea ({latest}). Update tea."
DOCTOR_DB_BAD = "Database: {detail}. Restore a backup or move the file away."
DOCTOR_PROMPTS_OK = "Prompts: {count} templates valid"
DOCTOR_PROMPTS_BAD = "Prompts: {detail}"
DOCTOR_TEMPLATES_OK = "Templates: theme and launcher files valid"
DOCTOR_TEMPLATES_BAD = "Templates: {detail}"
DOCTOR_DATA = "Data: database {db}, uploads {uploads} in {files}, log {log}"
DOCTOR_FILES = {1: "1 file"}
DOCTOR_FILES_MANY = "{count} files"
DOCTOR_SETTINGS_OK = "Settings: valid"
DOCTOR_SETTINGS_DEFAULT = "Settings: no file yet, using defaults"
DOCTOR_SETTINGS_BAD = "Settings: {detail}"
DOCTOR_AUTOSTART_OK = "Autostart: installed"
DOCTOR_AUTOSTART_MISSING = "Autostart: not installed. Run tea install-autostart to start at login."
DOCTOR_STATUS = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
